# 3rd party
from nose.tools import eq_

from django.test import modify_settings

# project
from ddtrace.constants import SAMPLING_PRIORITY_KEY
from ddtrace.contrib.django.conf import settings
from ddtrace.contrib.django import TraceMiddleware

# testing
from .compat import reverse
from .utils import DjangoTraceTestCase, override_ddtrace_settings


class DjangoMiddlewareTest(DjangoTraceTestCase):
    """
    Ensures that the middleware traces all Django internals
    """
    def test_middleware_trace_request(self):
        # ensures that the internals are properly traced
        url = reverse('users-list')
        response = self.client.get(url)
        eq_(response.status_code, 200)

        # check for spans
        spans = self.tracer.writer.pop()
        eq_(len(spans), 3)
        sp_request = spans[0]
        sp_template = spans[1]
        sp_database = spans[2]
        eq_(sp_database.get_tag('django.db.vendor'), 'sqlite')
        eq_(sp_template.get_tag('django.template_name'), 'users_list.html')
        eq_(sp_request.get_tag('http.status_code'), '200')
        eq_(sp_request.get_tag('http.url'), '/users/')
        eq_(sp_request.get_tag('django.user.is_authenticated'), 'False')
        eq_(sp_request.get_tag('http.method'), 'GET')

    def test_middleware_trace_errors(self):
        # ensures that the internals are properly traced
        url = reverse('forbidden-view')
        response = self.client.get(url)
        eq_(response.status_code, 403)

        # check for spans
        spans = self.tracer.writer.pop()
        eq_(len(spans), 1)
        span = spans[0]
        eq_(span.get_tag('http.status_code'), '403')
        eq_(span.get_tag('http.url'), '/fail-view/')
        eq_(span.resource, 'tests.contrib.django.app.views.ForbiddenView')

    def test_middleware_trace_function_based_view(self):
        # ensures that the internals are properly traced when using a function views
        url = reverse('fn-view')
        response = self.client.get(url)
        eq_(response.status_code, 200)

        # check for spans
        spans = self.tracer.writer.pop()
        eq_(len(spans), 1)
        span = spans[0]
        eq_(span.get_tag('http.status_code'), '200')
        eq_(span.get_tag('http.url'), '/fn-view/')
        eq_(span.resource, 'tests.contrib.django.app.views.function_view')

    def test_middleware_trace_error_500(self):
        # ensures we trace exceptions generated by views
        url = reverse('error-500')
        response = self.client.get(url)
        eq_(response.status_code, 500)

        # check for spans
        spans = self.tracer.writer.pop()
        eq_(len(spans), 1)
        span = spans[0]
        eq_(span.get_tag('http.status_code'), '500')
        eq_(span.get_tag('http.url'), '/error-500/')
        eq_(span.resource, 'tests.contrib.django.app.views.error_500')
        assert "Error 500" in span.get_tag('error.stack')

    def test_middleware_trace_callable_view(self):
        # ensures that the internals are properly traced when using callable views
        url = reverse('feed-view')
        response = self.client.get(url)
        eq_(response.status_code, 200)

        # check for spans
        spans = self.tracer.writer.pop()
        eq_(len(spans), 1)
        span = spans[0]
        eq_(span.get_tag('http.status_code'), '200')
        eq_(span.get_tag('http.url'), '/feed-view/')
        eq_(span.resource, 'tests.contrib.django.app.views.FeedView')

    def test_middleware_trace_partial_based_view(self):
        # ensures that the internals are properly traced when using a function views
        url = reverse('partial-view')
        response = self.client.get(url)
        eq_(response.status_code, 200)

        # check for spans
        spans = self.tracer.writer.pop()
        eq_(len(spans), 1)
        span = spans[0]
        eq_(span.get_tag('http.status_code'), '200')
        eq_(span.get_tag('http.url'), '/partial-view/')
        eq_(span.resource, 'partial')

    def test_middleware_trace_lambda_based_view(self):
        # ensures that the internals are properly traced when using a function views
        url = reverse('lambda-view')
        response = self.client.get(url)
        eq_(response.status_code, 200)

        # check for spans
        spans = self.tracer.writer.pop()
        eq_(len(spans), 1)
        span = spans[0]
        eq_(span.get_tag('http.status_code'), '200')
        eq_(span.get_tag('http.url'), '/lambda-view/')
        eq_(span.resource, 'tests.contrib.django.app.views.<lambda>')

    @modify_settings(
        MIDDLEWARE={
            'remove': 'django.contrib.auth.middleware.AuthenticationMiddleware',
        },
        MIDDLEWARE_CLASSES={
            'remove': 'django.contrib.auth.middleware.AuthenticationMiddleware',
        },
    )
    def test_middleware_without_user(self):
        # remove the AuthenticationMiddleware so that the ``request``
        # object doesn't have the ``user`` field
        url = reverse('users-list')
        response = self.client.get(url)
        eq_(response.status_code, 200)

        # check for spans
        spans = self.tracer.writer.pop()
        eq_(len(spans), 3)
        sp_request = spans[0]
        sp_template = spans[1]
        sp_database = spans[2]
        eq_(sp_request.get_tag('http.status_code'), '200')
        eq_(sp_request.get_tag('django.user.is_authenticated'), None)

    @override_ddtrace_settings(DISTRIBUTED_TRACING=True)
    def test_middleware_propagation(self):
        # ensures that we properly propagate http context
        url = reverse('users-list')
        headers = {
            'x-datadog-trace-id': '100',
            'x-datadog-parent-id': '42',
            'x-datadog-sampling-priority': '2',
        }
        response = self.client.get(url, **headers)
        eq_(response.status_code, 200)

        # check for spans
        spans = self.tracer.writer.pop()
        eq_(len(spans), 3)
        sp_request = spans[0]
        sp_template = spans[1]
        sp_database = spans[2]

        # Check for proper propagated attributes
        eq_(sp_request.trace_id, 100)
        eq_(sp_request.parent_id, 42)
        eq_(sp_request.get_metric(SAMPLING_PRIORITY_KEY), 2)

    def test_middleware_no_propagation(self):
        # ensures that we properly propagate http context
        url = reverse('users-list')
        headers = {
            'x-datadog-trace-id': '100',
            'x-datadog-parent-id': '42',
            'x-datadog-sampling-priority': '2',
        }
        response = self.client.get(url, **headers)
        eq_(response.status_code, 200)

        # check for spans
        spans = self.tracer.writer.pop()
        eq_(len(spans), 3)
        sp_request = spans[0]
        sp_template = spans[1]
        sp_database = spans[2]

        # Check that propagation didn't happen
        assert sp_request.trace_id != 100
        assert sp_request.parent_id != 42
        assert sp_request.get_metric(SAMPLING_PRIORITY_KEY) != 2
