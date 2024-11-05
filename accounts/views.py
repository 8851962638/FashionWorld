from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from core.models import Customer
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages

from django.shortcuts import render
# Create your views here.
def user_login(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')  # Ensure password is retrieved here
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('/')
        else:
            messages.error(request, "Invalid username or password")
            return redirect('user_login')

    return render(request, 'accounts/login.html')

def user_register(request):
    if request.method == "POST":
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        phone = request.POST.get('phone_field')

        # Debugging: Print values to console
        print(f"Username: {username}, Email: {email}, Password: {password}, Confirm Password: {confirm_password}, Phone: {phone}")

        if password == confirm_password:
            if User.objects.filter(username=username).exists():
                messages.error(request, "Username already exists")
                return redirect('user_register')
            elif User.objects.filter(email=email).exists():
                messages.error(request, "Email already exists")
                return redirect('user_register')
            else:
                user = User.objects.create_user(username=username, email=email, password=password)
                user.save()
                data = Customer(user=user, phone_field=phone)
                data.save()

                # Auto-login after registration
                our_user = authenticate(username=username, password=password)
                if our_user is not None:
                    login(request, our_user)
                    return redirect('/')
        else:
            messages.error(request, "Passwords do not match")
            return redirect('user_register')

    return render(request, 'accounts/register.html')

def user_logout(request):
    logout(request)
    return redirect('/')
