import { useEffect, useRef, useState, useCallback } from 'react';
import { Button } from '../ui/Button';

const MAX_TRANSCRIPT_LENGTH = 10000;

export function VoiceRecorder({ onTranscriptChange, initialTranscript = null }) {
  const recognitionRef = useRef(null);
  const transcriptRef = useRef(initialTranscript || '');
  const isListeningRef = useRef(false);
  const finalTranscriptRef = useRef('');
  const interimTranscriptRef = useRef('');

  const [status, setStatus] = useState('idle'); // idle | listening | processing | denied | error | ready
  const [confidence, setConfidence] = useState(null);
  const [showPreview, setShowPreview] = useState(false);
  const [editedTranscript, setEditedTranscript] = useState(initialTranscript || '');
  const [errorMessage, setErrorMessage] = useState('');

  // Keep refs updated
  useEffect(() => {
    transcriptRef.current = editedTranscript;
  }, [editedTranscript]);

  // Initialize SpeechRecognition
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setErrorMessage('Speech recognition not supported in this browser. Use Chrome, Edge, or Safari.');
      setStatus('error');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-IN'; // English (India) as primary
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      isListeningRef.current = true;
      setStatus('listening');
      setErrorMessage('');
      finalTranscriptRef.current = '';
      interimTranscriptRef.current = '';
    };

    recognition.onresult = (event) => {
      let interim = '';
      let final = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const transcript = result[0].transcript;
        if (result.isFinal) {
          final += transcript + ' ';
          // Use the confidence from the final result
          if (result[0].confidence !== undefined) {
            setConfidence(result[0].confidence);
          }
        } else {
          interim += transcript;
        }
      }

      finalTranscriptRef.current = final.trim();
      interimTranscriptRef.current = interim;

      // Show live preview during listening
      const liveText = (finalTranscriptRef.current + ' ' + interimTranscriptRef.current).trim();
      if (liveText) {
        setEditedTranscript(liveText);
      }
    };

    recognition.onerror = (event) => {
      isListeningRef.current = false;
      if (event.error === 'not-allowed' || event.error === 'permission-denied') {
        setStatus('denied');
        setErrorMessage('Microphone permission denied. Check browser settings and try again.');
      } else if (event.error === 'no-speech') {
        setErrorMessage('No speech detected. Please try speaking closer to the microphone.');
      } else if (event.error === 'audio-capture') {
        setErrorMessage('Audio capture failed. Check microphone connection.');
      } else {
        setErrorMessage(`Recognition error: ${event.error}`);
        setStatus('error');
      }
    };

    recognition.onend = () => {
      isListeningRef.current = false;
      if (status === 'listening') {
        // Recognition stopped without error - process final transcript
        const finalText = finalTranscriptRef.current.trim();
        if (finalText) {
          setEditedTranscript(finalText);
          setStatus('ready');
          setShowPreview(true);
        } else {
          setStatus('idle');
        }
      }
    };

    recognitionRef.current = recognition;

    return () => {
      recognition.stop();
      recognitionRef.current = null;
    };
  }, [status]);

  const startListening = useCallback(() => {
    if (!recognitionRef.current) {
      setErrorMessage('Speech recognition not initialized.');
      setStatus('error');
      return;
    }

    if (isListeningRef.current) return;

    // Clear previous transcript for fresh recording
    finalTranscriptRef.current = '';
    interimTranscriptRef.current = '';
    setConfidence(null);
    setShowPreview(false);
    setErrorMessage('');

    try {
      recognitionRef.current.start();
    } catch (error) {
      if (error.name === 'InvalidStateError') {
        // Already started, ignore
      } else {
        setErrorMessage(`Failed to start: ${error.message}`);
        setStatus('error');
      }
    }
  }, []);

  const stopListening = useCallback(() => {
    if (recognitionRef.current && isListeningRef.current) {
      recognitionRef.current.stop();
    }
  }, []);

  const acceptTranscript = useCallback(() => {
    const finalText = editedTranscript.trim();
    if (finalText) {
      onTranscriptChange?.({
        transcript: finalText,
        confidence: confidence,
      });
      setStatus('idle');
      setShowPreview(false);
    }
  }, [editedTranscript, confidence, onTranscriptChange]);

  const discardTranscript = useCallback(() => {
    setEditedTranscript('');
    setConfidence(null);
    setShowPreview(false);
    setStatus('idle');
    onTranscriptChange?.(null);
  }, [onTranscriptChange]);

  const retryTranscript = useCallback(() => {
    setEditedTranscript('');
    setConfidence(null);
    setShowPreview(false);
    setStatus('idle');
    setErrorMessage('');
  }, []);

  const getStatusText = () => {
    switch (status) {
      case 'listening': return '🎙️ Listening… Speak clearly into the microphone.';
      case 'processing': return 'Processing speech…';
      case 'ready': return `Transcript ready (confidence: ${confidence ? Math.round(confidence * 100) : 'N/A'}%). Review and accept or edit.`;
      case 'denied': return 'Microphone access denied. Enable in browser settings.';
      case 'error': return errorMessage || 'Speech recognition error.';
      default: return 'Press the button to start voice input.';
    }
  };

  const getStatusClass = () => {
    switch (status) {
      case 'listening': return 'text-red-300 animate-pulse';
      case 'ready': return 'text-green-300';
      case 'denied':
      case 'error': return 'text-red-300';
      case 'processing': return 'text-accent-amber';
      default: return 'text-text-muted';
    }
  };

  if (status === 'error' && errorMessage.includes('not supported')) {
    return (
      <section aria-labelledby="voice-recorder-title" className="bg-panel border border-border-default rounded-lg p-4">
        <h3 id="voice-recorder-title" className="font-semibold">Voice Input (Not Supported)</h3>
        <p className="text-sm text-text-muted mt-2">
          Speech recognition requires a modern browser (Chrome, Edge, Safari). Please use text input instead.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="voice-recorder-title" className="bg-panel border border-border-default rounded-lg p-4 space-y-4">
      <h3 id="voice-recorder-title" className="font-semibold">Voice Input (Optional)</h3>
      <p className="text-sm text-text-muted">
        Record your emergency report by voice. Transcript preview allows editing before submission.
        Uses browser SpeechRecognition (offline-capable, no API key). Accuracy varies by environment.
      </p>

      {/* Record Button */}
      <div className="space-y-2">
        <div className="flex gap-3 flex-wrap">
          <Button
            variant={status === 'listening' ? 'secondary' : 'primary'}
            size="lg"
            onClick={status === 'listening' ? stopListening : startListening}
            disabled={status === 'processing' || status === 'denied'}
            className={status === 'listening' ? 'bg-red-600 hover:bg-red-700' : ''}
          >
            {status === 'listening' ? (
              <>
                <svg className="animate-pulse -ml-1 mr-2 h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14.1 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z" />
                </svg>
                Stop Recording
              </>
            ) : (
              <>
                <svg className="-ml-1 mr-2 h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14.1 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z" />
                </svg>
                Start Voice Recording
              </>
            )}
          </Button>

          {status === 'ready' && (
            <Button variant="secondary" size="lg" onClick={retryTranscript}>
              <svg className="-ml-1 mr-2 h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                <path d="M21 12a9 9 0 1 1-9 9c2.52 0 4.93-1 6.74-2.74L21 8" />
              </svg>
              Retry
            </Button>
          )}
        </div>

        <p className={`text-sm ${getStatusClass()}`} role="status">{getStatusText()}</p>

        {status === 'denied' && (
          <p className="text-xs text-text-muted">
            To enable: Click the lock/microphone icon in the address bar → Allow microphone access → Refresh page.
          </p>
        )}

        {errorMessage && status !== 'denied' && status !== 'listening' && (
          <p className="text-xs text-red-300">{errorMessage}</p>
        )}
      </div>

      {/* Transcript Preview & Edit */}
      {(status === 'ready' || showPreview) && (
        <div className="space-y-3 border-t border-border-default pt-4">
          <label htmlFor="transcript-edit" className="block text-sm font-medium">
            Transcript Preview & Edit
          </label>
          <textarea
            id="transcript-edit"
            value={editedTranscript}
            onChange={(e) => setEditedTranscript(e.target.value.slice(0, MAX_TRANSCRIPT_LENGTH))}
            rows={4}
            maxLength={MAX_TRANSCRIPT_LENGTH}
            placeholder="Transcript will appear here after recording. You can edit before accepting."
            className="w-full bg-surface border border-border-default rounded-lg p-3 text-white resize-y"
          />
          <div className="flex flex-wrap gap-2 text-xs">
            <p className="text-text-muted">
              Characters: {editedTranscript.length}/{MAX_TRANSCRIPT_LENGTH}
              {confidence !== null && ` • Confidence: ${Math.round(confidence * 100)}%`}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="primary" size="md" onClick={acceptTranscript} disabled={!editedTranscript.trim()}>
              Accept Transcript
            </Button>
            <Button variant="ghost" size="md" onClick={discardTranscript}>
              Discard
            </Button>
          </div>
          <p className="text-xs text-text-muted">
            Review carefully. Speech recognition may mishear critical details (numbers, locations, names).
            Edit any errors before accepting.
          </p>
        </div>
      )}

      {/* Accepted Transcript Display */}
      {editedTranscript && status === 'idle' && !showPreview && (
        <div className="bg-surface border border-border-default rounded-lg p-3 space-y-1">
          <p className="font-medium text-sm">Accepted Transcript:</p>
          <p className="text-sm">{editedTranscript}</p>
          <p className="text-xs text-text-muted">
            {confidence !== null && `Confidence: ${Math.round(confidence * 100)}% • `}
            This transcript will be used for the emergency report.
          </p>
          <Button variant="ghost" size="sm" onClick={() => { setShowPreview(true); setStatus('ready'); }}>
            Edit Transcript
          </Button>
        </div>
      )}

      {!editedTranscript && status === 'idle' && !errorMessage.includes('not supported') && (
        <p className="text-xs text-text-muted text-center py-2">
          No voice transcript recorded. The report will use text input only.
        </p>
      )}
    </section>
  );
}