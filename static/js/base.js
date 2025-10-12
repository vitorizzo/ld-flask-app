/* document.addEventListener('DOMContentLoaded', function () {
  const container = document.getElementById('flash-message');
  if (!container) return;

  const alerts = Array.from(container.querySelectorAll('.alert'));
  alerts.forEach((el) => {
    // chiusura automatica dopo 4s
    setTimeout(() => {
      try {
        // usa la API di Bootstrap 5 per chiudere l'alert in modo pulito
        const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
        bsAlert.close();
      } catch (e) {
        // fallback: rimuovi manualmente
        el.classList.remove('show');
        setTimeout(() => el.remove(), 200);
      }
    }, 4000);
  });
}); */

const flash = document.getElementById('flash-message');
if (flash) {
    flash.scrollIntoView({ behavior: 'smooth', block: 'start' });
}