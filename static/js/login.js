document.addEventListener("DOMContentLoaded", () => {
  // التبديل بين علامات التبويب
  const tabBtns = document.querySelectorAll(".tab-btn")
  const tabPanes = document.querySelectorAll(".tab-pane")

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      // إزالة الفئة النشطة من جميع الأزرار واللوحات
      tabBtns.forEach((b) => b.classList.remove("active"))
      tabPanes.forEach((p) => p.classList.remove("active"))

      // إضافة الفئة النشطة إلى الزر المحدد واللوحة المقابلة
      btn.classList.add("active")
      const tabId = btn.getAttribute("data-tab")
      document.getElementById(tabId).classList.add("active")
    })
  })

  // التحقق من تطابق كلمات المرور
  const signupForm = document.getElementById("signupForm")
  if (signupForm) {
    const submitBtn = document.getElementById("signup-submit")

    signupForm.addEventListener("submit", async (e) => {
      e.preventDefault()

      // Disable submit button and show loading state
      submitBtn.disabled = true
      submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري إنشاء الحساب...'

      // Clear previous error messages
      document.querySelectorAll('.error-text').forEach(el => el.remove())
      document.querySelectorAll('.alert').forEach(el => el.remove())

      // Basic client-side validation
      const username = document.getElementById("signup-username").value.trim()
      const email = document.getElementById("email").value.trim()
      const password = document.getElementById("signup-password").value
      const confirmPassword = document.getElementById("confirm-password").value

      let hasError = false

      if (!username) {
        showError("signup-username", "يرجى إدخال اسم المستخدم")
        hasError = true
      }

      if (!email) {
        showError("email", "يرجى إدخال البريد الإلكتروني")
        hasError = true
      } else if (!isValidEmail(email)) {
        showError("email", "يرجى إدخال بريد إلكتروني صحيح")
        hasError = true
      }

      if (!password) {
        showError("signup-password", "يرجى إدخال كلمة المرور")
        hasError = true
      } else if (password.length < 8) {
        showError("signup-password", "يجب أن تكون كلمة المرور 8 أحرف على الأقل")
        hasError = true
      }

      if (!confirmPassword) {
        showError("confirm-password", "يرجى تأكيد كلمة المرور")
        hasError = true
      } else if (password !== confirmPassword) {
        showError("confirm-password", "كلمات المرور غير متطابقة")
        hasError = true
      }

      if (!hasError) {
        // Submit the form
        try {
          const formData = new FormData(signupForm)
          const response = await fetch(signupForm.action, {
            method: 'POST',
            body: formData,
            headers: {
              'X-Requested-With': 'XMLHttpRequest'
            }
          })

          if (response.ok) {
            // Redirect to login page on success
            window.location.href = '/login/'
          } else {
            const data = await response.json()
            if (data.errors) {
              Object.entries(data.errors).forEach(([field, errors]) => {
                showError(field, errors[0])
              })
            } else {
              showFormError("حدث خطأ أثناء إنشاء الحساب")
            }
          }
        } catch (error) {
          showFormError("حدث خطأ في الاتصال بالخادم")
        }
      }

      // Re-enable submit button
      submitBtn.disabled = false
      submitBtn.innerHTML = '<i class="fas fa-user-plus"></i> إنشاء حساب'
    })
  }

  // التحقق من صحة البريد الإلكتروني
  const emailInput = document.getElementById("email")
  if (emailInput) {
    emailInput.addEventListener("blur", () => {
      const email = emailInput.value
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
      if (email && !emailRegex.test(email)) {
        emailInput.setCustomValidity("يرجى إدخال بريد إلكتروني صحيح")
      } else {
        emailInput.setCustomValidity("")
      }
    })
  }

  // Helper functions
  function showError(fieldId, message) {
    const field = document.getElementById(fieldId)
    const errorDiv = document.createElement('div')
    errorDiv.className = 'error-text'
    errorDiv.textContent = message
    field.classList.add('error')
    field.parentNode.appendChild(errorDiv)
  }

  function showFormError(message) {
    const messagesDiv = document.querySelector('.messages') || document.createElement('div')
    messagesDiv.className = 'messages'

    const alertDiv = document.createElement('div')
    alertDiv.className = 'alert error'
    alertDiv.innerHTML = `<i class="fas fa-exclamation-circle"></i>${message}`

    messagesDiv.appendChild(alertDiv)
    signupForm.insertBefore(messagesDiv, signupForm.firstChild)
  }

  function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
  }
})
