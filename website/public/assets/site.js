const menu = document.querySelector('.menu-toggle');
const nav = document.querySelector('#navigation');
const closeMenu = () => {
  nav?.classList.remove('open');
  menu?.setAttribute('aria-expanded', 'false');
};
menu?.addEventListener('click', () => {
  const open = menu.getAttribute('aria-expanded') !== 'true';
  menu.setAttribute('aria-expanded', String(open));
  nav.classList.toggle('open', open);
});
nav?.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && menu?.getAttribute('aria-expanded') === 'true') {
    closeMenu(); menu.focus();
  }
});
const tabs = [...document.querySelectorAll('[role="tab"]')];
function activateTab(tab, focus = false) {
  tabs.forEach(item => {
    const active = item === tab;
    item.setAttribute('aria-selected', String(active));
    item.tabIndex = active ? 0 : -1;
    document.getElementById(item.getAttribute('aria-controls')).hidden = !active;
  });
  if (focus) tab.focus();
}
tabs.forEach((tab, index) => {
  tab.addEventListener('click', () => activateTab(tab));
  tab.addEventListener('keydown', event => {
    const indexes = {ArrowRight: (index + 1) % tabs.length,
      ArrowLeft: (index + tabs.length - 1) % tabs.length, Home: 0, End: tabs.length - 1};
    if (event.key in indexes) { event.preventDefault(); activateTab(tabs[indexes[event.key]], true); }
  });
});
async function loadRelease() {
  try {
    const response = await fetch('/release.json');
    if (!response.ok) return;
    const release = await response.json();
    if (!release.available || !/^[a-f0-9]{64}$/.test(release.sha256)) return;
    // Only the audited Nawam GitHub release. Reject arbitrary external URLs.
    if (release.url !== 'https://github.com/shannacore/nawam-releases/releases/download/v1.0.1/Nawam.exe') return;
    const button = document.getElementById('download-button');
    if (!button) return;
    button.href = release.url;
    button.setAttribute('download', 'Nawam.exe');
    button.textContent = 'Unduh Nawam untuk Windows ↓';
    document.getElementById('download-meta').textContent = `Versi ${release.version} · Windows x64 · ${(release.bytes / 1048576).toFixed(2)} MB`;
    document.getElementById('release-hash').textContent = release.sha256;
    const copy = document.getElementById('copy-hash');
    copy.disabled = false;
    copy.addEventListener('click', async () => {
      const status = document.getElementById('copy-status');
      try { await navigator.clipboard.writeText(release.sha256); status.textContent = 'Checksum berhasil disalin.'; }
      catch { status.textContent = 'Tidak dapat menyalin otomatis. Pilih teks checksum dan salin secara manual.'; }
    });
  } catch { /* Static status page remains useful if metadata cannot be loaded. */ }
}
loadRelease();
