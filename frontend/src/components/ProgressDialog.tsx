import React, { useEffect, useState } from 'react';
import { X, GitBranch, Database, FileText, Zap, CheckCircle, AlertCircle } from 'lucide-react';
import './ProgressDialog.css';

interface AnalysisProgress {
  status: string;
  message: string;
  current?: number;
  total?: number;
  stats?: any;
}

interface ProgressDialogProps {
  isOpen: boolean;
  repository: string;
  progress: AnalysisProgress | null;
  onCancel: () => void;
}

interface AnalysisStage {
  id: string;
  name: string;
  icon: React.ReactNode;
  weight: number; // Percentage of total progress
}

const ANALYSIS_STAGES: AnalysisStage[] = [
  { id: 'checking_cache', name: 'Checking Cache', icon: <Database size={16} />, weight: 5 },
  { id: 'cache_hit', name: 'Cache Hit', icon: <CheckCircle size={16} />, weight: 5 },
  { id: 'cloning', name: 'Cloning Repository', icon: <GitBranch size={16} />, weight: 15 },
  { id: 'parsing', name: 'Parsing Files', icon: <FileText size={16} />, weight: 40 },
  { id: 'chunking', name: 'Creating Chunks', icon: <Zap size={16} />, weight: 20 },
  { id: 'summarizing', name: 'AI Summarization', icon: <Zap size={16} />, weight: 15 },
  { id: 'indexing', name: 'Building Index', icon: <Database size={16} />, weight: 5 },
  { id: 'complete', name: 'Complete', icon: <CheckCircle size={16} />, weight: 0 },
];

export const ProgressDialog: React.FC<ProgressDialogProps> = ({
  isOpen,
  repository,
  progress,
  onCancel,
}) => {
  const [currentStageIndex, setCurrentStageIndex] = useState(0);
  const [overallProgress, setOverallProgress] = useState(0);
  const [stageProgress, setStageProgress] = useState(0);

  useEffect(() => {
    if (!progress) return;

    // Map backend status to frontend stage
    const mapStatusToStage = (status: string) => {
      switch (status) {
        case 'checking_cache':
          return 'checking_cache';
        case 'cache_hit':
          return 'cache_hit';
        case 'cloning':
        case 'cloning_complete':
          return 'cloning';
        case 'parsing':
        case 'parsing_progress':
          return 'parsing';
        case 'chunking':
        case 'chunking_complete':
          return 'chunking';
        case 'progress':
          // Check message to determine stage
          if (progress.message.includes('chunk')) {
            return 'chunking';
          } else if (progress.message.includes('summar')) {
            return 'summarizing';
          } else if (progress.message.includes('pars')) {
            return 'parsing';
          }
          return 'chunking'; // Default fallback
        case 'summarizing':
          return 'summarizing';
        case 'indexing':
          return 'indexing';
        case 'complete':
          return 'complete';
        default:
          return progress.status;
      }
    };

    const mappedStatus = mapStatusToStage(progress.status);
    const stageIndex = ANALYSIS_STAGES.findIndex(stage => stage.id === mappedStatus);
    
    if (stageIndex >= 0) {
      setCurrentStageIndex(stageIndex);
    }

    // Calculate overall progress
    let totalProgress = 0;
    
    // Add completed stages
    for (let i = 0; i < Math.min(stageIndex, ANALYSIS_STAGES.length - 1); i++) {
      totalProgress += ANALYSIS_STAGES[i].weight;
    }

    // Add current stage progress
    if (stageIndex >= 0 && stageIndex < ANALYSIS_STAGES.length - 1) {
      const currentStage = ANALYSIS_STAGES[stageIndex];
      let currentStagePercent = 0;

      // Calculate stage-specific progress
      if ((progress.status === 'parsing' || progress.status === 'parsing_progress') && progress.current && progress.total) {
        currentStagePercent = Math.min(progress.current / progress.total, 1);
      } else if (mappedStatus === 'cloning') {
        currentStagePercent = progress.status === 'cloning_complete' ? 1.0 : 0.7;
      } else if (mappedStatus === 'chunking') {
        currentStagePercent = progress.status === 'chunking_complete' ? 1.0 : 0.8;
      } else if (mappedStatus === 'summarizing') {
        currentStagePercent = 0.5;
      } else if (mappedStatus === 'indexing') {
        currentStagePercent = 0.8;
      } else if (mappedStatus === 'checking_cache') {
        currentStagePercent = 0.5;
      }

      totalProgress += currentStage.weight * currentStagePercent;
      setStageProgress(currentStagePercent * 100);
    }

    // Special case for complete status
    if (progress.status === 'complete') {
      totalProgress = 100;
      setStageProgress(100);
    }

    setOverallProgress(Math.min(totalProgress, 100));
  }, [progress]);

  if (!isOpen) return null;

  return (
    <div className="progress-dialog-overlay">
      <div className="progress-dialog">
        <div className="progress-dialog-header">
          <h2>
            <GitBranch size={20} />
            Analyzing Repository
          </h2>
          <button onClick={onCancel} className="progress-dialog-close">
            <X size={20} />
          </button>
        </div>

        <div className="progress-dialog-content">
          <div className="repository-info">
            <h3>{repository}</h3>
            <p>{progress?.message || 'Preparing analysis...'}</p>
          </div>

          <div className="progress-section">
            <div className="progress-bar-container">
              <div className="progress-bar">
                <div 
                  className="progress-bar-fill"
                  style={{ width: `${overallProgress}%` }}
                />
              </div>
              <span className="progress-percentage">{Math.round(overallProgress)}%</span>
            </div>

            {progress?.current && progress?.total && (
              <div className="progress-details">
                Processing {progress.current} of {progress.total} files
              </div>
            )}
          </div>

          <div className="stages-section">
            <h4>Analysis Stages</h4>
            <div className="stages-list">
              {ANALYSIS_STAGES.filter(stage => stage.id !== 'cache_hit').map((stage) => {
                const actualIndex = ANALYSIS_STAGES.findIndex(s => s.id === stage.id);
                const isCompleted = actualIndex < currentStageIndex;
                const isActive = actualIndex === currentStageIndex;
                const isError = progress?.status === 'error' && isActive;

                return (
                  <div
                    key={stage.id}
                    className={`stage-item ${isCompleted ? 'completed' : ''} ${isActive ? 'active' : ''} ${isError ? 'error' : ''}`}
                  >
                    <div className="stage-icon">
                      {isError ? <AlertCircle size={16} /> : stage.icon}
                    </div>
                    <div className="stage-info">
                      <span className="stage-name">{stage.name}</span>
                      {isActive && !isError && (
                        <div className="stage-progress">
                          <div className="stage-progress-bar">
                            <div 
                              className="stage-progress-fill"
                              style={{ width: `${stageProgress}%` }}
                            />
                          </div>
                        </div>
                      )}
                    </div>
                    <div className="stage-status">
                      {isCompleted && <CheckCircle size={16} className="stage-check" />}
                      {isActive && !isError && <div className="stage-spinner" />}
                      {isError && <AlertCircle size={16} className="stage-error" />}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};