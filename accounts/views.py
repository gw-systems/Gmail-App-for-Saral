from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from gmail_integration.models import GmailToken


def login_view(request):
    """Handle user login"""
    if request.user.is_authenticated:
        return redirect('inbox')
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {username}!')
                return redirect('inbox')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    
    return render(request, 'accounts/login.html', {'form': form})


def register_view(request):
    """Handle new user registration"""
    if request.user.is_authenticated:
        return redirect('inbox')
    
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created successfully for {username}! Please login.')
            return redirect('accounts:login')
        else:
            messages.error(request, 'Registration failed. Please fix the errors below.')
    else:
        form = UserCreationForm()
    
    return render(request, 'accounts/register.html', {'form': form})


def logout_view(request):
    """Handle user logout"""
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    return redirect('accounts:login')


@login_required
def profile_view(request):
    """Display user profile with connected Gmail accounts"""
    # Get user's connected Gmail accounts
    gmail_accounts = GmailToken.objects.filter(user=request.user, is_active=True)
    
    context = {
        'gmail_accounts': gmail_accounts,
        'active_page': 'profile'
    }
    
    return render(request, 'accounts/profile.html', context)
