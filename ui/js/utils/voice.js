// Voice Utils
class VoiceSystem {
    constructor() {
        this.recognition = null;
        this.isSupported = 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window;
        this.isRecording = false;
        
        if (this.isSupported) {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            this.recognition = new SpeechRecognition();
            this.recognition.continuous = false;
            this.recognition.interimResults = false;
        }
    }
    
    start(onResultCallback, onErrorCallback) {
        if (!this.isSupported) {
            if (onErrorCallback) onErrorCallback("Speech recognition not supported");
            return;
        }
        
        this.recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            if (onResultCallback) onResultCallback(transcript);
            this.isRecording = false;
        };
        
        this.recognition.onerror = (event) => {
            if (onErrorCallback) onErrorCallback(event.error);
            this.isRecording = false;
        };
        
        this.recognition.onend = () => {
            this.isRecording = false;
        };
        
        try {
            this.recognition.start();
            this.isRecording = true;
        } catch (e) {
            console.error(e);
            this.isRecording = false;
        }
    }
    
    stop() {
        if (this.isRecording && this.recognition) {
            this.recognition.stop();
        }
    }
}
const Voice = new VoiceSystem();
