let currentChannel = 'general';
let currentUserId = 0;
let currentUserName = '';
let eventSource = null;
let currentVoiceRoom = null;

function initCowork(channel, userId, userName) {
    currentChannel = channel;
    currentUserId = userId;
    currentUserName = userName || '';
    scrollToBottom();
    connectSSE();

    // Check if already in a voice channel and update UI
    var voiceData = localStorage.getItem('nodex_voice');
    if (voiceData) {
        try {
            var data = JSON.parse(voiceData);
            currentVoiceRoom = data.roomId;
            var controls = document.getElementById('voiceControls');
            if (controls) {
                controls.style.display = 'block';
                var nameEl = document.getElementById('voiceChannelName');
                if (nameEl) nameEl.textContent = data.channelName;
            }
        } catch (e) { }
    }
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
    eventSource.onmessage = function (e) {
        const msg = JSON.parse(e.data);
        appendMessage(msg);
    };
    eventSource.onerror = function () {
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channel: currentChannel, content: content }),
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
function joinVoice(roomId, btnElement) {
    if (btnElement) {
        if (btnElement.disabled) return;
        btnElement.disabled = true;
        btnElement.textContent = "Conectando...";
    }

    fetch('/cowork/voice/join/' + roomId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
    })
        .then(r => r.json())
        .then(data => {
            currentVoiceRoom = roomId;
            var channelName = roomId.replace(/-/g, ' ').replace(/\b\w/g, function (l) { return l.toUpperCase(); });

            // Save to localStorage for persistence across pages
            localStorage.setItem('nodex_voice', JSON.stringify({
                room: data.room,
                roomId: roomId,
                channelName: channelName,
                userName: currentUserName,
            }));

            // Show voice controls in cowork sidebar
            var controls = document.getElementById('voiceControls');
            if (controls) {
                controls.style.display = 'block';
                var nameEl = document.getElementById('voiceChannelName');
                if (nameEl) nameEl.textContent = channelName;
            }

            // Show the floating overlay (calls global function from base.html)
            showVoiceOverlay(data.room, channelName, currentUserName);

            // Reload page to update voice user indicators
            setTimeout(function () { window.location.reload(); }, 500);
        })
        .catch(() => {
            if (btnElement) {
                btnElement.disabled = false;
                btnElement.textContent = "Unirse";
            }
        });
}

function leaveVoice() {
    // Use the global leave function from base.html
    globalLeaveVoice();
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
