document.addEventListener("DOMContentLoaded", () => {
  // إعداد زر تسجيل الخروج
  setupLogout()

  // إعداد نموذج الإعدادات
  setupSettingsForm()
})

// إعداد نموذج الإعدادات
function setupSettingsForm() {
  const settingsForm = document.querySelector(".settings-container form")
  if (settingsForm) {
    settingsForm.addEventListener("submit", (e) => {
      e.preventDefault()

      const formData = new FormData(this)
      const data = {
        email_notifications: formData.get('email_notifications') === 'on',
        telegram_notifications: formData.get('telegram_notifications') === 'on',
        whatsapp_notifications: formData.get('whatsapp_notifications') === 'on',
        telegram_chat_id: formData.get('telegram_chat_id'),
        whatsapp_number: formData.get('whatsapp_number')
      }

      fetch('/dashboard/update_notification_settings/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify(data)
      })
        .then(response => response.json())
        .then(data => {
          if (data.status === 'success') {
            alert('تم حفظ الإعدادات بنجاح')
            window.location.reload() // Reload the page to show updated settings
          } else {
            alert(data.message || 'حدث خطأ أثناء حفظ الإعدادات')
          }
        })
        .catch(error => {
          console.error('Error:', error)
          alert('حدث خطأ أثناء حفظ الإعدادات')
        })
    })
  }

  // إضافة تأثيرات بصرية للتبديل بين الإعدادات
  const toggleSwitches = document.querySelectorAll(".switch input[type='checkbox']")
  toggleSwitches.forEach((toggle) => {
    toggle.addEventListener("change", function () {
      const settingItem = this.closest(".setting-item")
      if (this.checked) {
        settingItem.classList.add("active")
      } else {
        settingItem.classList.remove("active")
      }
    })
  })
}

// الحصول على رمز CSRF
function getCsrfToken() {
  const name = "csrftoken"
  let cookieValue = null
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";")
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim()
      if (cookie.substring(0, name.length + 1) === name + "=") {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1))
        break
      }
    }
  }
  return cookieValue
}

// إعداد زر تسجيل الخروج
function setupLogout() {
  const logoutForm = document.getElementById("logoutForm")
  if (logoutForm) {
    logoutForm.addEventListener("submit", function (e) {
      e.preventDefault()
      if (confirm("هل أنت متأكد أنك تريد تسجيل الخروج؟")) {
        this.submit()
      }
    })
  }
}
