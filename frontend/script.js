const form = document.querySelector('#subscribe-form');
const frequency = form.querySelector('[name="frequency"]');
const weeklyDay = form.querySelector('.weekly-day');
const formStatus = form.querySelector('.form-status');
const apiBase = 'https://tech-daily-newsletter-api.onrender.com';

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
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || 'We could not save your subscription.');
    formStatus.textContent = 'You are all set — your briefing is on its way.';
    form.reset();
    weeklyDay.hidden = true;
  } catch (error) {
    formStatus.className = 'form-status error';
    formStatus.textContent = error.message || 'Something went wrong. Please try again.';
  }
});
