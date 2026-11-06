export default function AlertThresholds() {
  return (
    <div className="space-y-5 max-w-2xl">
      <h2 className="text-2xl font-semibold tracking-tight text-ink">Research Alert Policy</h2>
      <p className="text-muted">Emergency delivery for the selected v1 model is disabled. Historical replay results are research outputs and do not create emergency notifications.</p>
      <div className="bg-surface border border-border rounded-card p-5 space-y-3 text-sm text-muted">
        <p>The model estimates rule-defined next-day environmental proxy classes. Its class scores are not calibrated probabilities of observed flooding.</p>
        <p>Operational alert thresholds and delivery require validated inputs, observed-flood evaluation and an approved stakeholder policy. No probability thresholds can be saved in this panel.</p>
        <p>Existing legacy alert history remains separate. The legacy alert screens are labelled as demo workflows.</p>
        <button type="button" disabled className="border border-border rounded-btn px-4 py-2 opacity-60 cursor-not-allowed">Operational policy approval required</button>
      </div>
    </div>
  )
}
