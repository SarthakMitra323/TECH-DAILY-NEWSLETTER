(() => {
  const form = document.querySelector('#subscribe-form');
  if (!form) return;

  const frequency = form.querySelector('[name="frequency"]');
  const weeklyDay = form.querySelector('.weekly-day');
  const formStatus = form.querySelector('.form-status');
  const apiBase = ['localhost', '127.0.0.1'].includes(location.hostname)
    ? 'http://localhost:8000'
    : 'https://tech-daily-newsletter-api.onrender.com';

  if (!frequency || !weeklyDay || !formStatus) return;

  frequency.addEventListener('change', () => {
    weeklyDay.hidden = frequency.value !== 'weekly';
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    formStatus.className = 'form-status';
    formStatus.textContent = 'Saving your preferences…';
    const data = Object.fromEntries(new FormData(form));
    if (data.frequency !== 'weekly') data.day_of_week = 'monday';
    try {
      const response = await fetch(`${apiBase}/api/register`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data),
      });
      const responseText = await response.text();
      let body = {};
      if (responseText) {
        try {
          body = JSON.parse(responseText);
        } catch {
          body = {detail: responseText};
        }
      }
      if (!response.ok) throw new Error(body.detail || 'We could not save your subscription.');
      formStatus.textContent = 'Check your inbox to confirm your subscription.';
      form.reset();
      weeklyDay.hidden = true;
    } catch (error) {
      formStatus.className = 'form-status error';
      formStatus.textContent = error.message || 'Something went wrong. Please try again.';
    }
  });
})();
