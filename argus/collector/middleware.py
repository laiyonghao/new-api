from django.contrib.auth import logout

from .models import UserSessionState


class SingleActiveSessionMiddleware:
	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		user = getattr(request, 'user', None)
		if user and user.is_authenticated:
			session_key = request.session.session_key or ''
			state = UserSessionState.objects.filter(user=user).only('active_session_key').first()
			if state and state.active_session_key and state.active_session_key != session_key:
				logout(request)
				request.argus_session_replaced = True
		return self.get_response(request)
