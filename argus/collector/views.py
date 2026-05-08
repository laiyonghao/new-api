from django.shortcuts import render

from .services.comparison import build_comparison_context


def comparison_view(request):
	context = {
		'page_title': '实时比价',
		**build_comparison_context(request.GET),
	}
	return render(request, 'collector/comparison.html', context)
