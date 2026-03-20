from django.shortcuts import render

def render_home(request):
    return render(request, 'home.html')

def render_about(request):
    return render(request, 'about.html')