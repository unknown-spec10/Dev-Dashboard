import React, { useState } from 'react';
import axios from 'axios';
import { Play, Loader2, FileCode, Layers } from 'lucide-react';

export default function JobSubmitForm({ onJobSubmitted, apiKey }) {
  const [taskName, setTaskName] = useState('sleep_task');
  const [priority, setPriority] = useState('default');
  const [duration, setDuration] = useState(10);
  const [repoUrl, setRepoUrl] = useState('https://github.com/google/sentence-transformers');
  const [inputText, setInputText] = useState(
    "SentenceTransformers is a Python framework for state-of-the-art sentence, text and image embeddings.\n\n" +
    "You can use this framework to compute sentence / text embeddings for more than 100 languages.\n\n" +
    "This framework can be easily integrated with databases like pgvector to run codebase semantic searches.\n\n" +
    "Let's test this v4 text chunking and embedding pipeline in our new Dev Dashboard!"
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError('');
    
    try {
      let payloadData = {};
      if (taskName === 'sleep_task') {
        payloadData = { duration: Number(duration) };
      } else if (taskName === 'repo_ingestion') {
        payloadData = { repo_url: repoUrl };
      } else if (taskName === 'embedding_pipeline') {
        payloadData = { text: inputText };
      }

      const payload = {
        name: taskName,
        priority: priority,
        payload: payloadData
      };
      
      const config = {
        headers: {
          Authorization: `Bearer ${apiKey}`
        }
      };
      
      const response = await axios.post('/api/jobs/', payload, config);
      onJobSubmitted(response.data);
    } catch (err) {
      console.error(err);
      setError(err.response?.data?.detail || 'Failed to submit job. Check if the backend is running and your API Key matches database records.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="bg-slate-900/40 backdrop-blur-md border border-slate-800/80 rounded-xl p-6 shadow-xl relative overflow-hidden">
      {/* Top gradient accent */}
      <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500"></div>
      
      <h2 className="text-xl font-bold mb-4 text-white flex items-center gap-2">
        <Play size={18} className="text-blue-400" /> Submit New Job
      </h2>
      
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Task Template */}
        <div>
          <label className="block text-sm font-medium text-slate-400 mb-1">
            Task Template
          </label>
          <select 
            value={taskName}
            onChange={(e) => setTaskName(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition cursor-pointer"
          >
            <option value="sleep_task">Dummy Sleep Task</option>
            <option value="repo_ingestion">Codebase Repo Ingestion</option>
            <option value="embedding_pipeline">pgvector Embedding Pipeline</option>
          </select>
        </div>

        {/* Priority Selection */}
        <div>
          <label className="block text-sm font-medium text-slate-400 mb-1">
            Priority Queue
          </label>
          <div className="grid grid-cols-3 gap-2">
            {['low', 'default', 'high'].map((p) => {
              const active = priority === p;
              let btnColor = "border-slate-800 hover:bg-slate-850/60";
              if (active) {
                if (p === 'low') btnColor = "bg-slate-800/45 border-slate-600 text-slate-300 ring-2 ring-slate-500/25";
                if (p === 'default') btnColor = "bg-blue-950/40 border-blue-900/70 text-blue-400 ring-2 ring-blue-500/20";
                if (p === 'high') btnColor = "bg-red-950/30 border-red-900/70 text-red-400 ring-2 ring-red-500/20";
              }
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPriority(p)}
                  className={`border font-semibold py-1.5 px-2 rounded-lg text-xs capitalize transition cursor-pointer text-center ${btnColor}`}
                >
                  {p}
                </button>
              );
            })}
          </div>
        </div>

        {/* Dynamic Inputs */}
        {taskName === 'sleep_task' && (
          <div className="transition-all">
            <label className="block text-sm font-medium text-slate-400 mb-1">
              Duration (seconds)
            </label>
            <input
              type="number"
              min="1"
              max="120"
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
              required
            />
            <p className="text-xs text-slate-500 mt-1">
              Task runs in background, checking for cancellations cooperatively.
            </p>
          </div>
        )}

        {taskName === 'repo_ingestion' && (
          <div className="transition-all">
            <label className="block text-sm font-medium text-slate-400 mb-1 flex items-center gap-1.5">
              <FileCode size={14} className="text-blue-400" /> GitHub Repository URL
            </label>
            <input
              type="url"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              className="w-full bg-slate-950 border border-slate-850 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition font-mono text-xs"
              required
            />
            <p className="text-xs text-slate-500 mt-1">
              Simulates repository code analysis file-by-file with cancellation hooks.
            </p>
          </div>
        )}

        {taskName === 'embedding_pipeline' && (
          <div className="transition-all">
            <label className="block text-sm font-medium text-slate-400 mb-1 flex items-center gap-1.5">
              <Layers size={14} className="text-blue-400" /> Text Content for Chunking
            </label>
            <textarea
              rows={4}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              className="w-full bg-slate-950 border border-slate-850 rounded-lg px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 transition text-xs leading-relaxed"
              required
            />
            <p className="text-xs text-slate-500 mt-1">
              Splits text into paragraphs, generates 1536-d float vectors, and upserts to pgvector database.
            </p>
          </div>
        )}
        
        {error && (
          <div className="text-xs bg-red-950/40 border border-red-900/60 rounded-lg px-3 py-2 text-red-400 leading-normal">
            {error}
          </div>
        )}
        
        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold py-2 px-4 rounded-lg flex items-center justify-center gap-2 transition-all transform hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="animate-spin" size={18} />
              Enqueuing...
            </>
          ) : (
            <>
              <Play size={18} fill="currentColor" className="text-white" />
              Run Job
            </>
          )}
        </button>
      </form>
    </div>
  );
}
