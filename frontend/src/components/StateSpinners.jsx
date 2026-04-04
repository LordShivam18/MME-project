export const LoadingSpinner = () => (
  <div style={{ padding: '2rem', textAlign: 'center', color: '#555' }}>
    <div className="spinner">Loading data...</div>
  </div>
);

export const ErrorState = ({ message }) => (
  <div style={{ padding: '1rem', border: '1px solid red', backgroundColor: '#ffe6e6', color: '#c00', borderRadius: '4px', margin: '1rem 0' }}>
    <strong>System Error:</strong> {message}
  </div>
);

export const EmptyState = ({ message, suggestion }) => (
  <div style={{ padding: '3rem', textAlign: 'center', border: '1px dashed #ccc', borderRadius: '8px', color: '#666' }}>
    <h3>{message}</h3>
    {suggestion && <p>{suggestion}</p>}
  </div>
);
