document.addEventListener("DOMContentLoaded", () => {
  // إعداد المرشحات
  setupFilters()

  // إعداد زر تسجيل الخروج
  setupLogout()
})

// إعداد مرشحات التنبيهات
function setupFilters() {
  const severityFilter = document.getElementById("filter-severity")
  const readFilter = document.getElementById("filter-read")

  if (severityFilter && readFilter) {
    severityFilter.addEventListener("change", applyFilters)
    readFilter.addEventListener("change", applyFilters)
  }
}

// تطبيق المرشحات على التنبيهات
function applyFilters() {
  const severityFilter = document.getElementById("filter-severity").value
  const readFilter = document.getElementById("filter-read").value
  const alertCards = document.querySelectorAll(".alert-card")

  alertCards.forEach((card) => {
    const severity = card.getAttribute("data-severity")
    const isRead = card.getAttribute("data-read")

    const showBySeverity = severityFilter === "all" || severity === severityFilter
    const showByRead =
      readFilter === "all" ||
      (readFilter === "read" && isRead === "true") ||
      (readFilter === "unread" && isRead === "false")

    if (showBySeverity && showByRead) {
      card.style.display = "block"
    } else {
      card.style.display = "none"
    }
  })
}

// وضع علامة على التنبيه كمقروء
function markAlertRead(alertId) {
  fetch(`/mark_alert_read/${alertId}/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.status === "success") {
        const alertCard = document.querySelector(`[data-alert-id="${alertId}"]`)
        if (alertCard) {
          alertCard.classList.remove("unread")
          alertCard.classList.add("read")
          alertCard.setAttribute("data-read", "true")

          // إزالة زر وضع علامة كمقروء
          const markReadBtn = alertCard.querySelector(".mark-read-btn")
          if (markReadBtn) {
            markReadBtn.remove()
          }

          // إعادة تطبيق المرشحات
          applyFilters()
        }
      }
    })
    .catch((error) => console.error("Error marking alert as read:", error))
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
