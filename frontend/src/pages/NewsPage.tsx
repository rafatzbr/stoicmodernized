import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Paper,
  Snackbar,
  Stack,
  Typography,
  CircularProgress,
  Checkbox,
  FormControlLabel,
  Divider,
  TextField,
  Tooltip,
  Badge,
} from '@mui/material';
import {
  fetchNews,
  saveSelectedNews,
  getSelectedNews,
  clearSelectedNews,
  generateFromSelectedNews,
} from '../api';
import type { NewsStory } from '../api/client';

type Notice = {
  message: string;
  severity: 'success' | 'info' | 'warning' | 'error';
};

function getArticleParagraphs(story: NewsStory) {
  const content = story.content || story.summary || story.snippet || '';
  return content
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

export function NewsPage() {
  const [stories, setStories] = useState<NewsStory[]>([]);
  const [selectedIndices, setSelectedIndices] = useState<number[]>([]);
  const [fetching, setFetching] = useState(false);
  const [fetchingMore, setFetchingMore] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [channel] = useState('ai-signal');
  const [topic, setTopic] = useState('AI news');
  const [expandedStory, setExpandedStory] = useState<string | null>(null);

  const showNotice = useCallback((message: string, severity: Notice['severity'] = 'info') => {
    setNotice({ message, severity });
  }, []);

  // Load previously selected stories on mount
  useEffect(() => {
    void loadSelected();
  }, []);

  const loadSelected = async () => {
    try {
      const result = await getSelectedNews(channel);
      setSelectedIndices(
        result.stories.map((s) => stories.findIndex((st) => st.url === s.url)).filter((i) => i >= 0)
      );
    } catch {
      // No session yet — ignore
    }
  };

  const handleFetch = async () => {
    setFetching(true);
    try {
      const result = await fetchNews(channel, false);
      setStories(result.stories);
      setSelectedIndices([]);
      showNotice(`Fetched ${result.count} AI news stories`, 'success');
    } catch (error: any) {
      showNotice(error?.response?.data?.detail || 'Failed to fetch news', 'error');
    } finally {
      setFetching(false);
    }
  };

  const handleFetchMore = async () => {
    setFetchingMore(true);
    try {
      const result = await fetchNews(channel, true);
      setStories(result.stories);
      const added = result.added_count ?? 0;
      showNotice(added ? `Added ${added} more stories` : 'No new stories found', added ? 'success' : 'info');
    } catch (error: any) {
      showNotice(error?.response?.data?.detail || 'Failed to fetch more news', 'error');
    } finally {
      setFetchingMore(false);
    }
  };

  const handleToggleSelect = useCallback((index: number) => {
    setSelectedIndices((prev) => {
      if (prev.includes(index)) {
        return prev.filter((i) => i !== index);
      }
      if (prev.length >= 5) {
        showNotice('Maximum 5 stories selected', 'warning');
        return prev;
      }
      return [...prev, index];
    });
  }, [showNotice]);

  const handleSelectAll = useCallback(() => {
    const available = 5 - selectedIndices.length;
    if (available <= 0) {
      showNotice('Maximum 5 stories selected', 'warning');
      return;
    }
    const newIndices = stories
      .map((_, i) => i)
      .filter((i) => !selectedIndices.includes(i))
      .slice(0, available);
    setSelectedIndices((prev) => [...prev, ...newIndices]);
  }, [stories, selectedIndices, showNotice]);

  const handleClear = async () => {
    try {
      await clearSelectedNews(channel);
      setSelectedIndices([]);
      setStories([]);
      showNotice('Cleared', 'info');
    } catch {
      showNotice('Failed to clear', 'error');
    }
  };

  const handleGenerate = async () => {
    if (selectedIndices.length === 0) {
      showNotice('Select at least one story', 'warning');
      return;
    }
    setGenerating(true);
    try {
      await saveSelectedNews(channel, selectedIndices);
      const result = await generateFromSelectedNews({
        channel,
        topic,
        video_mode: 'short',
        provider: 'edge',
        renderer: 'remotion',
        skip_upload: false,
      });
      showNotice(`Video generation + upload started: ${result.run_id}`, 'success');
    } catch (error: any) {
      showNotice(error?.response?.data?.detail || 'Failed to generate video', 'error');
    } finally {
      setGenerating(false);
    }
  };

  const canGenerate = selectedIndices.length > 0 && !generating;

  return (
    <Box sx={{ minHeight: '100vh', px: { xs: 2, md: 4 }, py: { xs: 2, md: 3 } }}>
      <Stack spacing={3}>
        {/* Header */}
        <Paper sx={{ p: { xs: 2, md: 3 }, border: '1px solid', borderColor: 'divider' }}>
          <Stack spacing={2}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                AI Signal News
              </Typography>
              <Box sx={{ flexGrow: 1 }} />
              <Badge badgeContent={selectedIndices.length} color="primary">
                <Button
                  variant="outlined"
                  disabled={fetching || fetchingMore || generating}
                  onClick={handleFetch}
                  startIcon={fetching ? <CircularProgress size={18} /> : null}
                >
                  Fetch AI News
                </Button>
              </Badge>
            </Stack>

            {/* Topic input */}
            <TextField
              label="Topic keyword"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              fullWidth
              size="small"
              placeholder="AI news"
            />

            {/* Selection controls */}
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="body2" color="text.secondary">
                {selectedIndices.length}/5 selected
              </Typography>
              <Button size="small" onClick={handleSelectAll} disabled={selectedIndices.length >= 5}>
                Select up to 5
              </Button>
              <Button
                size="small"
                onClick={handleFetchMore}
                disabled={stories.length === 0 || fetching || fetchingMore || generating}
                startIcon={fetchingMore ? <CircularProgress size={14} /> : null}
              >
                Fetch more
              </Button>
              <Button size="small" color="error" onClick={handleClear} disabled={stories.length === 0}>
                Clear
              </Button>
              <Box sx={{ flexGrow: 1 }} />
              <Button
                variant="contained"
                disabled={!canGenerate}
                onClick={handleGenerate}
                startIcon={generating ? <CircularProgress size={18} color="inherit" /> : null}
              >
                Generate & Upload Video
              </Button>
            </Stack>
          </Stack>
        </Paper>

        {/* Story cards */}
        {stories.length === 0 && !fetching && (
          <Paper sx={{ p: 4, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              Click "Fetch AI News" to load the latest AI stories.
            </Typography>
          </Paper>
        )}

        {fetching && (
          <Paper sx={{ p: 4, textAlign: 'center' }}>
            <CircularProgress sx={{ mb: 2 }} />
            <Typography variant="body2" color="text.secondary">
              Fetching stories and article content…
            </Typography>
          </Paper>
        )}

        <Stack spacing={2}>
          {stories.map((story, index) => {
            const isSelected = selectedIndices.includes(index);
            const isExpanded = expandedStory === story.url;
            const paragraphs = getArticleParagraphs(story);

            return (
              <Paper
                key={story.url}
                sx={{
                  p: 2,
                  border: isSelected ? '2px solid' : '1px solid',
                  borderColor: isSelected ? 'primary.main' : 'divider',
                  bgcolor: isSelected ? 'action.selected' : 'background.paper',
                  transition: 'all 0.2s',
                }}
              >
                <Stack spacing={1}>
                  <Stack direction="row" spacing={1} alignItems="flex-start">
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={isSelected}
                          onChange={() => handleToggleSelect(index)}
                          disabled={generating || (!isSelected && selectedIndices.length >= 5)}
                        />
                      }
                      label=""
                      sx={{ mr: 0, mt: 0.5 }}
                    />
                    <Stack sx={{ flexGrow: 1 }}>
                      <Typography
                        variant="subtitle1"
                        sx={{ fontWeight: 600, cursor: 'pointer' }}
                        onClick={() => setExpandedStory(isExpanded ? null : story.url)}
                      >
                        {story.title}
                      </Typography>
                      {story.original_title && story.original_title !== story.title ? (
                        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                          Search result title: {story.original_title}
                        </Typography>
                      ) : null}
                      <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                        <Chip
                          label={story.source}
                          size="small"
                          variant="outlined"
                          sx={{ fontSize: '0.7rem', height: 20 }}
                        />
                        <Chip
                          label={`Relevance: ${(story.relevance * 100).toFixed(0)}%`}
                          size="small"
                          sx={{
                            fontSize: '0.7rem',
                            height: 20,
                            bgcolor: story.relevance > 0.85 ? 'success.lighter' : 'info.lighter',
                          }}
                        />
                        <Tooltip title={story.url}>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ cursor: 'pointer' }}
                            onClick={(e) => {
                              e.stopPropagation();
                              window.open(story.url, '_blank');
                            }}
                          >
                            ↗
                          </Typography>
                        </Tooltip>
                      </Stack>
                    </Stack>
                  </Stack>

                  {isExpanded && (
                    <>
                      <Divider />
                      <Stack spacing={1.25}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                          Article content
                        </Typography>
                        {paragraphs.length > 0 ? (
                          <Stack spacing={1.4}>
                            {paragraphs.map((paragraph, paragraphIndex) => (
                              <Typography
                                // eslint-disable-next-line react/no-array-index-key
                                key={paragraphIndex}
                                variant="body2"
                                color="text.secondary"
                                sx={{ lineHeight: 1.75 }}
                              >
                                {paragraph}
                              </Typography>
                            ))}
                          </Stack>
                        ) : (
                          <Typography variant="body2" color="text.secondary">
                            No article content available. Open the source link to read it.
                          </Typography>
                        )}
                      </Stack>
                    </>
                  )}
                </Stack>
              </Paper>
            );
          })}
        </Stack>
      </Stack>

      <Snackbar
        open={Boolean(notice)}
        autoHideDuration={3500}
        onClose={() => setNotice(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert onClose={() => setNotice(null)} severity={notice?.severity ?? 'info'} variant="filled" sx={{ width: '100%' }}>
          {notice?.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
