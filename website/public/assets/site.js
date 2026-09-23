const language = document.documentElement.lang.toLowerCase().split('-')[0] === 'en' ? 'en' : 'id';
const messages = {
  id: {
    download: 'Unduh Nawam untuk Windows ↓', version: 'Versi',
    copied: 'Checksum berhasil disalin.',
    copyFailed: 'Tidak dapat menyalin otomatis. Pilih teks checksum dan salin secara manual.'
  },
  en: {
    download: 'Download Nawam for Windows ↓', version: 'Version',
    copied: 'Checksum copied.',
    copyFailed: 'Could not copy automatically. Select the checksum and copy it manually.'
  }
}[language];
// The page and its counterpart share section IDs; never forward text fragments or query data.
const languageLinks = [...document.querySelectorAll('[data-language-link]')].map(link => ({
  link, path: link.getAttribute('href').split('#')[0]
}));
function updateLanguageLinks() {
  const hash = window.location.hash;
  const fragment = /^#[a-zA-Z][a-zA-Z0-9_-]*$/.test(hash) &&
    document.getElementById(hash.slice(1)) ? hash : '';
  languageLinks.forEach(({link, path}) => link.setAttribute('href', path + fragment));
}
updateLanguageLinks();
window.addEventListener('hashchange', updateLanguageLinks);

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
function validRelease(release) {
  if (!release || typeof release !== 'object' || Array.isArray(release)) return false;
  if (release.available !== true || release.architecture !== 'x64') return false;
  if (typeof release.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(release.sha256)) return false;
  if (!Number.isSafeInteger(release.bytes) || release.bytes <= 0) return false;
  if (typeof release.version !== 'string' || !/^[0-9]+\.[0-9]+\.[0-9]+$/.test(release.version)) return false;
  // Keep this audited release pin in step with the static download links when publishing.
  const approvedURL = 'https://github.com/shannacore/nawam-releases/releases/download/v1.0.1/Nawam.exe';
  if (typeof release.url !== 'string' || release.url !== approvedURL) return false;
  const url = new URL(release.url);
  return url.protocol === 'https:' && url.host === 'github.com' &&
    !url.username && !url.password && !url.search && !url.hash &&
    url.pathname === `/shannacore/nawam-releases/releases/download/v${release.version}/Nawam.exe`;
}
async function loadRelease() {
  const button = document.getElementById('download-button');
  if (!button) return;
  try {
    const response = await fetch('/release.json');
    if (!response.ok) return;
    const release = await response.json();
    if (!validRelease(release)) return;
    button.href = release.url;
    button.setAttribute('download', 'Nawam.exe');
    button.textContent = messages.download;
    document.getElementById('download-meta').textContent = `${messages.version} ${release.version} · Windows x64 · ${(release.bytes / 1048576).toFixed(2)} MB`;
    document.getElementById('release-hash').textContent = release.sha256;
    const copy = document.getElementById('copy-hash');
    copy.disabled = false;
    copy.addEventListener('click', async () => {
      const status = document.getElementById('copy-status');
      try { await navigator.clipboard.writeText(release.sha256); status.textContent = messages.copied; }
      catch { status.textContent = messages.copyFailed; }
    });
  } catch { /* Retain trusted static links and checksum guidance when metadata cannot be loaded. */ }
}
loadRelease();
