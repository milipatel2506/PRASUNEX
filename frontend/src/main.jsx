import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import '@fontsource/lexend/500.css'
import '@fontsource/lexend/600.css'
import '@fontsource/source-sans-3/400.css'
import '@fontsource/source-sans-3/600.css'
import '@fontsource/noto-sans-gujarati/400.css'
import '@fontsource/noto-sans-gujarati/600.css'
import '@fontsource/noto-sans-devanagari/400.css'
import '@fontsource/noto-sans-devanagari/600.css'
import './styles.css'

class Boundary extends React.Component {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (this.state.failed) {
      return <div role="alert" style={{ padding: 32, fontFamily: 'sans-serif' }}><h2>Something went wrong.</h2><p>Please reload the page.</p></div>
    }
    return this.props.children
  }
}

createRoot(document.getElementById('root')).render(<Boundary><App /></Boundary>)
