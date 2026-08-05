/* KWS关键词唤醒测试工具 - 全局公共脚本 */

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    console.log('KWS Test Tool loaded');
    initEditableSelects();
});

function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, char => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        "'": '&#39;',
        '"': '&quot;'
    }[char]));
}

function initEditableSelects(root = document) {
    root.querySelectorAll('.editable-select').forEach(select => {
        if (select.dataset.initialized === 'true') return;

        const input = select.querySelector('input');
        const toggle = select.querySelector('.editable-select-toggle');
        const menu = select.querySelector('.editable-select-menu');
        if (!input || !toggle || !menu) return;

        Object.assign(select.style, { position: 'relative' });
        input.style.paddingRight = '36px';
        Object.assign(toggle.style, {
            position: 'absolute',
            top: '1px',
            right: '1px',
            width: '34px',
            height: 'calc(100% - 2px)',
            border: '0',
            borderLeft: '1px solid var(--border)',
            borderRadius: '0 var(--radius) var(--radius) 0',
            background: 'transparent',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            fontSize: '14px'
        });
        Object.assign(menu.style, {
            display: 'none',
            position: 'absolute',
            zIndex: '30',
            top: 'calc(100% + 4px)',
            left: '0',
            right: '0',
            maxHeight: '220px',
            overflowY: 'auto',
            padding: '6px 0',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            background: 'var(--card)',
            boxShadow: 'var(--shadow-lg)'
        });

        const options = JSON.parse(select.dataset.options || '[]');
        menu.innerHTML = options.map(option => (
            `<button type="button" class="editable-select-option" data-value="${escapeHtml(option)}">${escapeHtml(option)}</button>`
        )).join('');
        menu.querySelectorAll('.editable-select-option').forEach(option => {
            Object.assign(option.style, {
                display: 'block',
                width: '100%',
                padding: '9px 12px',
                border: '0',
                background: 'transparent',
                color: 'var(--text)',
                cursor: 'pointer',
                fontSize: '14px',
                textAlign: 'left'
            });
        });

        const openMenu = () => {
            select.classList.add('open');
            menu.style.display = 'block';
        };
        const closeMenu = () => {
            select.classList.remove('open');
            menu.style.display = 'none';
        };

        input.addEventListener('focus', openMenu);
        input.addEventListener('click', openMenu);
        input.addEventListener('keydown', event => {
            if (event.key === 'Escape') closeMenu();
        });
        toggle.addEventListener('click', () => {
            const wasOpen = select.classList.contains('open');
            input.focus();
            select.classList.toggle('open', !wasOpen);
        });
        menu.addEventListener('mousedown', event => event.preventDefault());
        menu.addEventListener('click', event => {
            const option = event.target.closest('.editable-select-option');
            if (!option) return;
            input.value = option.dataset.value;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            closeMenu();
        });
        document.addEventListener('click', event => {
            if (!select.contains(event.target)) closeMenu();
        });

        select.dataset.initialized = 'true';
    });
}

window.initEditableSelects = initEditableSelects;

// 工具函数
const Utils = {
    formatTime(seconds) {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    },
    
    formatDateTime(dateStr) {
        const d = new Date(dateStr);
        return d.toLocaleString('zh-CN');
    },
    
    debounce(fn, delay) {
        let timer = null;
        return function(...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), delay);
        };
    }
};

// 全局暴露
window.Utils = Utils;
