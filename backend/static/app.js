document.querySelectorAll('[data-copy]').forEach((btn) => {
    btn.addEventListener('click', async () => {
        const code = btn.parentElement.querySelector('code').innerText;
        try {
            await navigator.clipboard.writeText(code);
            btn.textContent = 'Copied';
            setTimeout(() => (btn.textContent = 'Copy'), 1200);
        } catch (e) {
            btn.textContent = 'Failed';
            setTimeout(() => (btn.textContent = 'Copy'), 1200);
        }
    });
});
