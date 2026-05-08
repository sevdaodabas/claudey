from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class RegisterViewTests(TestCase):
    def test_register_get_renders_form(self):
        response = self.client.get(reverse("register"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertIn("form", response.context)

    def test_register_post_creates_and_logs_in_user(self):
        response = self.client.post(
            reverse("register"),
            data={
                "username": "new-user",
                "password1": "strong-test-password-123",
                "password2": "strong-test-password-123",
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("home"))
        self.assertTrue(get_user_model().objects.filter(username="new-user").exists())
        self.assertIn("_auth_user_id", self.client.session)

    def test_register_post_with_invalid_data_does_not_create_user(self):
        response = self.client.post(
            reverse("register"),
            data={
                "username": "bad-user",
                "password1": "short",
                "password2": "different",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="bad-user").exists())
        self.assertIn("form", response.context)
