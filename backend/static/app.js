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

const themeToggle = document.querySelector('[data-theme-toggle]');
const themeLabel = themeToggle?.querySelector('.theme-toggle__label');
const themeIcon = themeToggle?.querySelector('.theme-toggle__icon');

const applyTheme = (theme) => {
    document.body.dataset.theme = theme;
    const isDark = theme === 'dark';
    if (themeToggle) themeToggle.setAttribute('aria-pressed', String(isDark));
    if (themeLabel) themeLabel.textContent = isDark ? 'Dark' : 'Light';
    if (themeIcon) themeIcon.textContent = isDark ? 'D' : 'L';
};

const initTheme = () => {
    const stored = localStorage.getItem('theme');
    if (stored === 'dark' || stored === 'light') {
        applyTheme(stored);
        return;
    }
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    applyTheme(prefersDark ? 'dark' : 'light');
};

initTheme();

if (themeToggle) {
    themeToggle.addEventListener('click', () => {
        const next = document.body.dataset.theme === 'dark' ? 'light' : 'dark';
        localStorage.setItem('theme', next);
        applyTheme(next);
    });
}

const dropZone = document.querySelector('[data-drop-zone]');
const fileInput = document.querySelector('#fileInput');
const pickBtn = document.querySelector('[data-pick]');
const uploadBtn = document.querySelector('[data-upload-btn]');
const clearBtn = document.querySelector('[data-clear-btn]');
const uploadList = document.querySelector('[data-upload-list]');
const uploadStatus = document.querySelector('[data-upload-status]');

const uploadItems = [];
let isUploading = false;

const formatBytes = (bytes) => {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let value = bytes;
    let index = 0;
    while (value >= 1024 && index < units.length - 1) {
        value /= 1024;
        index += 1;
    }
    return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[index]}`;
};

const setStatus = (text, isError = false) => {
    if (!uploadStatus) return;
    uploadStatus.textContent = text;
    uploadStatus.style.color = isError ? '#b71c1c' : '';
};

const updateControls = () => {
    const hasItems = uploadItems.length > 0;
    if (uploadBtn) uploadBtn.disabled = !hasItems || isUploading;
    if (clearBtn) clearBtn.disabled = !hasItems || isUploading;
};

const renderUploads = () => {
    if (!uploadList) return;
    uploadList.innerHTML = '';
    uploadItems.forEach((item) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'upload-item';
        wrapper.dataset.id = item.id;

        const header = document.createElement('div');
        header.className = 'upload-item-header';

        const name = document.createElement('div');
        name.className = 'upload-name';
        name.textContent = item.file.name;

        const meta = document.createElement('div');
        meta.className = 'upload-meta';
        meta.textContent = `${formatBytes(item.file.size)} · ${item.status}`;

        header.appendChild(name);
        header.appendChild(meta);

        const progress = document.createElement('div');
        progress.className = 'upload-progress';
        const bar = document.createElement('div');
        bar.className = 'upload-progress-bar';
        bar.style.width = `${item.progress}%`;
        progress.appendChild(bar);

        wrapper.appendChild(header);
        wrapper.appendChild(progress);

        if (item.link) {
            const link = document.createElement('a');
            link.className = 'upload-link';
            link.href = item.link;
            link.target = '_blank';
            link.rel = 'noreferrer';
            link.textContent = item.link;
            wrapper.appendChild(link);
        }

        uploadList.appendChild(wrapper);
    });
    updateControls();
};

const updateItem = (id, updates) => {
    const item = uploadItems.find((entry) => entry.id === id);
    if (!item) return;
    Object.assign(item, updates);
    const itemEl = uploadList?.querySelector(`.upload-item[data-id="${id}"]`);
    if (itemEl) {
        const meta = itemEl.querySelector('.upload-meta');
        if (meta) meta.textContent = `${formatBytes(item.file.size)} · ${item.status}`;
        const bar = itemEl.querySelector('.upload-progress-bar');
        if (bar) bar.style.width = `${item.progress}%`;
        const existingLink = itemEl.querySelector('.upload-link');
        if (item.link && !existingLink) {
            const link = document.createElement('a');
            link.className = 'upload-link';
            link.href = item.link;
            link.target = '_blank';
            link.rel = 'noreferrer';
            link.textContent = item.link;
            itemEl.appendChild(link);
        }
    }
};

const addFiles = (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    files.forEach((file) => {
        uploadItems.push({
            id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
            file,
            status: 'Ready',
            progress: 0,
            link: ''
        });
    });
    setStatus(`${files.length} file(s) added.`);
    renderUploads();
};

const extractErrorMessage = (xhr) => {
    const raw = (xhr.responseText || '').trim();
    if (raw) return raw.split('\n')[0];
    return xhr.statusText || `Error ${xhr.status}`;
};

const uploadSingle = (item) => new Promise((resolve) => {
    const formData = new FormData();
    formData.append('file', item.file, item.file.name);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/upload');

    xhr.upload.addEventListener('progress', (event) => {
        if (!event.lengthComputable) return;
        const percent = Math.round((event.loaded / event.total) * 100);
        updateItem(item.id, { progress: percent, status: 'Uploading' });
    });

    xhr.addEventListener('load', () => {
        if (xhr.status === 200) {
            const lines = xhr.responseText.trim().split('\n');
            const link = lines[0] || '';
            updateItem(item.id, { progress: 100, status: 'Uploaded', link });
        } else {
            const message = extractErrorMessage(xhr);
            updateItem(item.id, { status: message, progress: 100 });
            setStatus(message, true);
        }
        resolve();
    });

    xhr.addEventListener('error', () => {
        updateItem(item.id, { status: 'Upload failed', progress: 100 });
        setStatus('Upload failed. Please try again.', true);
        resolve();
    });

    updateItem(item.id, { status: 'Starting', progress: 0 });
    xhr.send(formData);
});

const uploadQueue = async () => {
    if (isUploading || uploadItems.length === 0) return;
    isUploading = true;
    setStatus('Uploading files...');
    updateControls();

    for (const item of uploadItems) {
        if (item.status === 'Uploaded') continue;
        await uploadSingle(item);
    }

    isUploading = false;
    setStatus('Uploads complete.');
    updateControls();
};

if (pickBtn && fileInput) {
    pickBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (event) => addFiles(event.target.files));
}

if (dropZone) {
    ['dragenter', 'dragover'].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
            event.preventDefault();
            event.stopPropagation();
            dropZone.classList.add('is-dragover');
        });
    });

    ['dragleave', 'drop'].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
            event.preventDefault();
            event.stopPropagation();
            dropZone.classList.remove('is-dragover');
        });
    });

    dropZone.addEventListener('drop', (event) => {
        const files = event.dataTransfer?.files;
        if (files) addFiles(files);
    });
}

if (uploadBtn) {
    uploadBtn.addEventListener('click', uploadQueue);
}

if (clearBtn) {
    clearBtn.addEventListener('click', () => {
        if (isUploading) return;
        uploadItems.length = 0;
        uploadList.innerHTML = '';
        setStatus('Upload list cleared.');
        updateControls();
    });
}
