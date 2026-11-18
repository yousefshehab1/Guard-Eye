from django import forms
from .models import Camera, NotificationSettings


class CameraForm(forms.ModelForm):
    """نموذج لإضافة وتعديل الكاميرات."""

    class Meta:
        model = Camera
        fields = ["name", "location", "camera_index", "camera_url"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "اسم الكاميرا"}
            ),
            "location": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "موقع الكاميرا"}
            ),
            "camera_index": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "فهرس الكاميرا (إذا كانت متصلة مباشرة)"}
            ),
            "camera_url": forms.URLInput(
                attrs={"class": "form-control", "placeholder": "رابط الكاميرا (إذا كانت IP Camera)"}
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        camera_index = cleaned_data.get("camera_index")
        camera_url = cleaned_data.get("camera_url")

        if camera_index is None and not camera_url:
            raise forms.ValidationError(
                "يجب تحديد إما فهرس الكاميرا أو رابط الكاميرا."
            )
        if camera_index is not None and camera_url:
            raise forms.ValidationError(
                "لا يمكن تحديد كل من فهرس الكاميرا ورابط الكاميرا في نفس الوقت."
            )
        return cleaned_data


class NotificationSettingsForm(forms.ModelForm):
    """نموذج لإعدادات الإشعارات."""

    class Meta:
        model = NotificationSettings
        fields = [
            "email_notifications",
            "telegram_notifications",
            "telegram_username",
            "telegram_chat_id",
            "whatsapp_notifications",
            "whatsapp_number",
            "notification_interval",
        ]
        widgets = {
            "email_notifications": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "telegram_notifications": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "telegram_username": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "اسم المستخدم في تليجرام (اختياري)",
                }
            ),
            "telegram_chat_id": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "معرف دردشة تليجرام (اختياري)",
                }
            ),
            "whatsapp_notifications": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "whatsapp_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "رقم الواتساب مع رمز البلد (مثال: +971501234567)",
                }
            ),
            "notification_interval": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "max": 3600}
            ),
        }


class UserRegistrationForm(forms.Form):
    """نموذج لتسجيل مستخدم جديد."""

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "اسم المستخدم"}
        ),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "البريد الإلكتروني"}
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "كلمة المرور"}
        )
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "تأكيد كلمة المرور"}
        )
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("كلمات المرور غير متطابقة")

        return cleaned_data


class LoginForm(forms.Form):
    """نموذج لتسجيل الدخول."""

    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "اسم المستخدم أو البريد الإلكتروني",
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "كلمة المرور"}
        )
    )
    remember_me = forms.BooleanField(
        required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )
