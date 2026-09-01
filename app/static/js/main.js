// Script interactivo Vanilla JS para notificaciones en tiempo real y checklists asíncronos

document.addEventListener('DOMContentLoaded', () => {
    // Inicializar polling de notificaciones si el usuario está autenticado
    if (document.getElementById('notifBadge')) {
        checkNotifications();
        setInterval(checkNotifications, 15000); // Polling cada 15 segundos
    }
});

// Función para consultar notificaciones no leídas vía AJAX
function checkNotifications() {
    fetch('/api/notifications/unread')
        .then(response => response.json())
        .then(data => {
            const badge = document.getElementById('notifBadge');
            const listContainer = document.getElementById('notifList');

            if (!badge || !listContainer) return;

            if (data.unread_count > 0) {
                badge.textContent = data.unread_count;
                badge.classList.remove('d-none');
            } else {
                badge.classList.add('d-none');
            }

            if (data.notifications.length === 0) {
                listContainer.innerHTML = '<li class="dropdown-item text-muted text-center py-2">Sin notificaciones pendientes</li>';
            } else {
                listContainer.innerHTML = data.notifications.map(n => `
                    <li class="notification-item p-2 d-flex justify-content-between align-items-start">
                        <div>
                            <p class="mb-1 text-dark fw-bold">${escapeHtml(n.mensaje)}</p>
                            <small class="text-muted">${n.fecha}</small>
                        </div>
                        <button onclick="markNotificationRead(${n.id})" class="btn btn-sm btn-outline-success ms-2" title="Marcar como leída">
                            <i class="bi bi-check"></i>
                        </button>
                    </li>
                `).join('');
            }
        })
        .catch(err => console.error('Error al cargar notificaciones:', err));
}

// Marca una notificación individual como leída
function markNotificationRead(notifId) {
    fetch(`/api/notifications/${notifId}/read`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            checkNotifications();
        }
    })
    .catch(err => console.error('Error al marcar notificación:', err));
}

// Toggle de ítem de checklist asíncrono
function toggleChecklistItem(taskId, itemId) {
    fetch(`/api/task/${taskId}/checklist/${itemId}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            // Actualizar barra de progreso de la tarea si existe en el DOM
            const progressBar = document.getElementById(`task-progress-${taskId}`);
            const progressText = document.getElementById(`task-progress-text-${taskId}`);
            const statusBadge = document.getElementById(`task-status-badge-${taskId}`);

            if (progressBar) {
                progressBar.style.width = `${data.nuevo_porcentaje}%`;
                progressBar.setAttribute('aria-valuenow', data.nuevo_porcentaje);
            }
            if (progressText) {
                progressText.textContent = `${data.nuevo_porcentaje}%`;
            }
            if (statusBadge) {
                statusBadge.textContent = data.nuevo_estado;
            }
        }
    })
    .catch(err => console.error('Error al cambiar checklist:', err));
}

// Utilidad para escapar texto HTML
function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

