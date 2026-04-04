import React from 'react';

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, errorMessage: '' };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, errorMessage: error.message };
  }

  componentDidCatch(error, errorInfo) {
    console.error("Global UI Crash Trapped natively by React:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '3rem', textAlign: 'center', fontFamily: 'sans-serif' }}>
          <h2>Application Layout Crash Detected</h2>
          <p style={{ color: 'red', margin: '1rem 0' }}>{this.state.errorMessage}</p>
          <button 
            onClick={() => window.location.href = "/"} 
            style={{ padding: '0.5rem 1rem', background: '#333', color: 'white', border: 'none', cursor: 'pointer' }}
          >
            Force Restart Dashboard
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
