from r3sourcer.apps.login.tasks import send_login_sms


class LoginService:

    def send_login_sms(self, contact, redirect_url=None):
        send_login_sms.delay(contact.id, redirect_url)
