import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { App } from './ui/App'
import { RepoDetail } from './ui/RepoDetail'

const root = createRoot(document.getElementById('root')!)
root.render(
	<BrowserRouter>
		<Routes>
			<Route path="/" element={<App />} />
			<Route path="/repos/:name" element={<RepoDetail />} />
		</Routes>
	</BrowserRouter>
)
