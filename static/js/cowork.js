let currentChannel = 'general';
let currentUserId = 0;
let eventSource = null;

function initCowork(channel, userId) {
    currentChannel = channel;
    currentUserId = userId;
    scrollToBottom();
    connectSSE();
}

function connectSSE() {
    if (eventSource) eventSource.close();

    const container = document.getElementById('messagesContainer');
    const msgs = container.querySelectorAll('.cowork-msg');
    let lastId = 0;
    if (msgs.length > 0) {
        const lastMsg = msgs[msgs.length - 1];
        lastId = lastMsg.dataset.id || 0;
    }

    eventSource = new EventSource('/cowork/stream?channel=' + currentChannel + '&last_id=' + lastId);
    eventSource.onmessage = function(e) {
        const msg = JSON.parse(e.data);
        appendMessage(msg);
    };
    eventSource.onerror = function() {
        eventSource.close();
        setTimeout(connectSSE, 5000);
    };
}

function appendMessage(msg) {
    const container = document.getElementById('messagesContainer');

    // Remove empty state if present
    const empty = container.querySelector('.cowork-empty');
    if (empty) empty.remove();

    // Check if message already exists
    if (container.querySelector('[data-id="' + msg.id + '"]')) return;

    const isOwn = msg.sender_id === currentUserId;
    const div = document.createElement('div');
    div.className = 'cowork-msg' + (isOwn ? ' cowork-msg-own' : '');
    div.dataset.id = msg.id;
    div.innerHTML =
        '<div class="cowork-msg-avatar">' + msg.sender.substring(0, 2).toUpperCase() + '</div>' +
        '<div class="cowork-msg-body">' +
            '<div class="cowork-msg-meta">' +
                '<span class="cowork-msg-name">' + msg.sender + '</span>' +
                '<span class="cowork-msg-time">' + msg.created_at + '</span>' +
            '</div>' +
            '<div class="cowork-msg-text">' + escapeHtml(msg.content) + '</div>' +
        '</div>';
    container.appendChild(div);
    scrollToBottom();
}

function sendMessage(e) {
    e.preventDefault();
    const input = document.getElementById('chatInput');
    const content = input.value.trim();
    if (!content) return false;

    input.value = '';
    fetch('/cowork/send', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({channel: currentChannel, content: content}),
    })
    .then(r => r.json())
    .then(msg => {
        if (msg.error) {
            input.value = content;
        }
    })
    .catch(() => { input.value = content; });
    return false;
}

function startCall() {
    const projectId = currentChannel.startsWith('project_')
        ? currentChannel.replace('project_', '')
        : null;

    fetch('/cowork/call/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({project_id: projectId}),
    })
    .then(r => r.json())
    .then(data => {
        window.location.href = '/cowork/call/' + data.room;
    });
}

function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    if (container) container.scrollTop = container.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
