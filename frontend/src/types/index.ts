export type Job = {
  job_id: string;
  topic: string;
  status: string;
  created_at: string;
  channel?: string;
  channel_name?: string;
  video_path?: string;
  thumbnail_path?: string;
  subtitle_path?: string;
};

export type RunState = {
  run_id: string;
  running: boolean;
  returncode: number | null;
  cmd: string[];
  lines: string[];
};

export type JobAsset = {
  path: string;
  relative: string;
  size: number;
  mime?: string;
  url?: string;
};

export type JobDetail = {
  job_id: string;
  topic: string;
  status: string;
  created_at: string;
  channel?: string;
  channel_name?: string;
  channel_handle?: string;
  channel_description?: string;
  video_path?: string;
  thumbnail_path?: string;
  subtitle_path?: string;
  research_path?: string;
  script_path?: string;
  scene_plan_path?: string;
  audio_path?: string;
  images_dir?: string;
  metadata_path?: string;
  assets: JobAsset[];
};
