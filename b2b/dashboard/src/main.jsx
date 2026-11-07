import { createRoot } from 'react-dom/client'
import { enableDevValidations } from 'ag-grid-community'
import App from './App.jsx'
import './styles.css'

if (import.meta.env.DEV) enableDevValidations()

createRoot(document.getElementById('root')).render(<App />)
