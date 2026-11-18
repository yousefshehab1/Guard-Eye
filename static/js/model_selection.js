document.addEventListener('DOMContentLoaded', function() {
    const modelSelectionForm = document.getElementById('modelSelectionForm');
    const errorMessage = document.getElementById('error-message');
    
    if (modelSelectionForm) {
        modelSelectionForm.addEventListener('submit', function(e) {
            // التحقق من اختيار نموذج
            const selectedModel = document.querySelector('input[name="model"]:checked');
            
            if (!selectedModel) {
                e.preventDefault();
                errorMessage.style.display = 'block';
            } else {
                errorMessage.style.display = 'none';
            }
        });
    }
    
    // إخفاء رسالة الخطأ عند اختيار نموذج
    const modelInputs = document.querySelectorAll('input[name="model"]');
    modelInputs.forEach(input => {
        input.addEventListener('change', function() {
            errorMessage.style.display = 'none';
        });
    });
});