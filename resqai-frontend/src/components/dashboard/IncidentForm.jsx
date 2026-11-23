import { useEffect, useRef, useState, useCallback } from 'react';
import { api } from '../../services/api';
import { Button } from '../ui/Button';
import { LocationCapture } from './LocationCapture';
import { VoiceRecorder } from './VoiceRecorder';

export function IncidentForm({ onCreated }) {
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [location, setLocation] = useState(null);
  const [transcript, setTranscript] = useState(null);
  const inFlight = useRef(false);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const handleLocationChange = useCallback((newLocation) => {
    setLocation(newLocation);
  }, []);

  const handleTranscriptChange = useCallback((transcriptData) => {
    setTranscript(transcriptData);
  }, []);

  // Combine text report with transcript if available
  const getCombinedReport = useCallback(() => {
    let combined = description.trim();
    if (transcript?.transcript) {
      const transcriptText = transcript.transcript.trim();
      if (transcriptText) {
        if (combined) {
          combined += `\n\n[Voice Transcript] ${transcriptText}`;
        } else {
          combined = transcriptText;
        }
      }
    }
    return combined;
  }, [description, transcript]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (inFlight.current) return;

    const report = getCombinedReport();
    if (!report) {
      setError('Enter an incident report or record a voice transcript before submitting.');
      return;
    }

    inFlight.current = true;
    setSubmitting(true);
    setError('');
    try {
      const incident = await api.createIncident({ report });
      if (!incident?.incident_id) throw new Error('The API did not return an incident ID. Check Incident History before retrying.');

      // Update location if provided
      if (location) {
        await api.updateIncidentLocation(incident.incident_id, location);
      }

      // Update transcript if provided
      if (transcript) {
        await api.updateIncidentTranscript(incident.incident_id, transcript);
      }

      if (mounted.current) {
        setDescription('');
        setLocation(null);
        setTranscript(null);
        onCreated?.(incident);
      }
    } catch (failure) {
      if (mounted.current) setError(failure.message);
    } finally {
      inFlight.current = false;
      if (mounted.current) setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} aria-busy={submitting} className="bg-panel border border-border-default rounded-lg p-4 space-y-4">
      <label htmlFor="incident-report" className="block font-semibold">Incident Report</label>
      <textarea
        id="incident-report"
        required
        maxLength={10000}
        aria-describedby="report-help"
        disabled={submitting}
        className="w-full bg-surface border border-border-default rounded-lg p-3 text-white"
        rows={6}
        placeholder="Describe what happened, the location, and any reported injuries. Do not guess missing details."
        value={description}
        onChange={(event) => setDescription(event.target.value)}
      />
      <p id="report-help" className="text-sm text-text-muted">Only include information needed for this demonstration. Maximum 10,000 characters.</p>

      {/* Location Capture Component */}
      <LocationCapture onLocationChange={handleLocationChange} initialLocation={location} />

      {/* Voice Recorder Component */}
      <VoiceRecorder onTranscriptChange={handleTranscriptChange} initialTranscript={transcript} />

      {error && <p role="alert" className="text-red-300">{error}</p>}
      <Button type="submit" disabled={submitting || !getCombinedReport()}>
        {submitting ? 'Processing report…' : 'Submit Incident'}
      </Button>
      {submitting && (
        <p role="status" className="text-sm text-text-muted">
          Running the multi-agent assessment. No emergency services will be dispatched.
        </p>
      )}
    </form>
  );
}