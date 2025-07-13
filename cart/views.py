from django.shortcuts import render

# Create your views here.
def cart(request):
    #TODO: add cart logic
    return render(request, 'basket.html')