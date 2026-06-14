import React from 'react';
import { Ban, Eye, Database, Clock, ArrowUp, ArrowDown } from 'lucide-react';

export default function JobTable({ jobs, selectedJobId, onSelectJob, onCancelJob }) {
  const getStatusBadge = (status) => {
    switch (status) {
      case 'PENDING':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-950/60 text-blue-400 border border-blue-900/50">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-400" />
            PENDING
          </span>
        );
      case 'RUNNING':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-950/60 text-amber-400 border border-amber-900/50">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
            RUNNING
          </span>
        );
      case 'DONE':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950/60 text-emerald-400 border border-emerald-900/50">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            DONE
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-950/60 text-red-400 border border-red-900/50">
            <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
            FAILED
          </span>
        );
      case 'CANCELLED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800/60 text-slate-400 border border-slate-700/50">
            <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
            CANCELLED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-slate-400">
            {status}
          </span>
        );
    }
  };

  const getPriorityBadge = (priority) => {
    switch (priority) {
      case 'high':
        return (
          <span className="inline-flex items-center gap-1 text-red-400 font-bold text-xs uppercase bg-red-950/15 border border-red-900/40 px-2 py-0.5 rounded-md">
            <ArrowUp size={12} className="stroke-[3]" /> High
          </span>
        );
      case 'low':
        return (
          <span className="inline-flex items-center gap-1 text-slate-400 font-medium text-xs uppercase bg-slate-850 border border-slate-800 px-2 py-0.5 rounded-md">
            <ArrowDown size={12} /> Low
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 text-blue-400 font-medium text-xs uppercase bg-blue-950/20 border border-blue-900/40 px-2 py-0.5 rounded-md">
            Default
          </span>
        );
    }
  };

  const formatTime = (dateString) => {
    try {
      const d = new Date(dateString);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return dateString;
    }
  };

  if (jobs.length === 0) {
    return (
      <div className="bg-slate-900/30 border border-slate-800/80 rounded-xl p-12 text-center shadow-lg">
        <Database size={48} className="mx-auto text-slate-650 mb-3" />
        <h3 className="text-lg font-medium text-slate-300">No jobs submitted yet</h3>
        <p className="text-sm text-slate-500 mt-1">Submit a job using the panel on the left to start execution.</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-900/40 backdrop-blur-md border border-slate-800/80 rounded-xl overflow-hidden shadow-xl">
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-800/80 bg-slate-950/40 text-slate-400 text-xs font-semibold uppercase tracking-wider">
              <th className="py-3.5 px-4">Job ID</th>
              <th className="py-3.5 px-4">Task Name</th>
              <th className="py-3.5 px-4">Status</th>
              <th className="py-3.5 px-4">Priority</th>
              <th className="py-3.5 px-4">Progress</th>
              <th className="py-3.5 px-4">Payload</th>
              <th className="py-3.5 px-4">Time</th>
              <th className="py-3.5 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/40 text-sm text-slate-300">
            {jobs.map((job) => {
              const isSelected = selectedJobId === job.id;
              const isTerminal = ['DONE', 'FAILED', 'CANCELLED'].includes(job.status);
              const progress = job.progress || 0;
              
              return (
                <tr 
                  key={job.id} 
                  className={`hover:bg-slate-800/20 transition-colors cursor-pointer ${
                    isSelected ? 'bg-blue-950/15 border-l-2 border-l-blue-500' : ''
                  }`}
                  onClick={() => onSelectJob(job.id)}
                >
                  <td className="py-3.5 px-4 font-mono text-xs text-slate-400">
                    {job.id.substring(0, 8)}...
                  </td>
                  <td className="py-3.5 px-4 font-semibold text-white font-mono text-xs">
                    {job.name}
                  </td>
                  <td className="py-3.5 px-4">
                    {getStatusBadge(job.status)}
                  </td>
                  <td className="py-3.5 px-4">
                    {getPriorityBadge(job.priority)}
                  </td>
                  {/* Progress Bar Column */}
                  <td className="py-3.5 px-4 min-w-[130px]">
                    <div className="flex items-center gap-2">
                      <div className="w-full bg-slate-950 rounded-full h-1.5 overflow-hidden border border-slate-850">
                        <div 
                          className={`h-full transition-all duration-500 rounded-full ${
                            job.status === 'RUNNING' 
                              ? 'bg-gradient-to-r from-blue-500 to-indigo-500 animate-pulse' 
                              : job.status === 'DONE' 
                                ? 'bg-emerald-500' 
                                : job.status === 'FAILED' 
                                  ? 'bg-red-500' 
                                  : 'bg-slate-700'
                          }`}
                          style={{ width: `${progress}%` }}
                        ></div>
                      </div>
                      <span className="text-xs font-mono font-medium text-slate-400 w-8 text-right">
                        {progress}%
                      </span>
                    </div>
                  </td>
                  <td className="py-3.5 px-4 font-mono text-xs text-slate-450 max-w-[120px] truncate">
                    {JSON.stringify(job.payload)}
                  </td>
                  <td className="py-3.5 px-4 text-xs text-slate-400">
                    <div className="flex items-center gap-1.5">
                      <Clock size={12} className="text-slate-500" />
                      {formatTime(job.created_at)}
                    </div>
                  </td>
                  <td className="py-3.5 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => onSelectJob(job.id)}
                        className={`p-1.5 rounded-lg text-slate-400 hover:text-blue-400 hover:bg-slate-800/60 transition ${
                          isSelected ? 'text-blue-400 bg-slate-800/60' : ''
                        }`}
                        title="View Logs"
                      >
                        <Eye size={16} />
                      </button>
                      <button
                        onClick={() => onCancelJob(job.id)}
                        disabled={isTerminal}
                        className={`p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-slate-800/60 transition disabled:opacity-30 disabled:cursor-not-allowed`}
                        title="Cancel Job"
                      >
                        <Ban size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
