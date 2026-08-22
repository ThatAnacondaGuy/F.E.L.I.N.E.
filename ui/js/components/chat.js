
window.Components.chat = () => {
    return `
        <div class="page-header">
            <h2>Meow OS Intelligence</h2>
        </div>
        <div class="chat-container">
            <div class="chat-messages" id="chat-messages">
                <div class="chat-bubble chat-bubble-ai">
                    Hello Aniket. I'm ready to assist you. Your schedule indicates you have AI class soon.
                </div>
            </div>
            <div class="chat-input-area">
                <input type="text" class="input" id="chat-input" placeholder="Ask anything, query your memory, or give a command...">
                <button class="btn btn-icon btn-ghost" id="chat-voice" title="Voice Input">🎤</button>
                <button class="btn btn-primary" id="chat-send">Send</button>
            </div>
        </div>
    `;
};

window.Components.chatAfterRender = () => {
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send');
    const messages = document.getElementById('chat-messages');
    
    const sendMsg = () => {
        const text = input.value.trim();
        if (!text) return;
        
        messages.innerHTML += `<div class="chat-bubble chat-bubble-user">${text}</div>`;
        input.value = '';
        messages.scrollTop = messages.scrollHeight;
        
        // Mock response
        setTimeout(() => {
            messages.innerHTML += `<div class="chat-bubble chat-bubble-ai">Processing your request regarding "${text}"...</div>`;
            messages.scrollTop = messages.scrollHeight;
        }, 1000);
    };
    
    sendBtn.addEventListener('click', sendMsg);
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMsg();
    });
};
