from django.test import TestCase
from django.urls import reverse
from users.models import User


class AuthenticationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')

    def test_login_page_renders(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)

    def test_successful_login(self):
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 302)

    def test_failed_login(self):
        response = self.client.post(reverse('login'), {
        'username': 'testuser',
        'password': 'wrongpassword',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'non corretti')

    def test_logout_requires_post(self):
        # LogoutView built-in richiede POST, non GET
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('logout'))
        self.assertNotEqual(response.status_code, 200)

    def test_signup_creates_custom_user(self):
        response = self.client.post(reverse('signup'), {
            'username': 'newuser',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newuser').exists())


class ProfileViewsTestCase(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='testpass123')
        self.user2 = User.objects.create_user(username='user2', password='testpass123')

    def test_private_profile_requires_login(self):
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 302)

    def test_private_profile_shows_own_data_only(self):
        # get_object() deve sempre restituire l'utente loggato, mai un altro
        self.client.login(username='user1', password='testpass123')
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.context['profile_user'], self.user1)

    def test_public_profile_accessible_without_login(self):
        # Il profilo pubblico deve essere visibile a chiunque, anche anonimi
        response = self.client.get(reverse('public-profile', args=['user1']))
        self.assertEqual(response.status_code, 200)

    def test_navbar_shows_login_when_anonymous(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Login')
        self.assertNotContains(response, 'Logout')

    def test_navbar_shows_username_when_authenticated(self):
        self.client.login(username='user1', password='testpass123')
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'user1')