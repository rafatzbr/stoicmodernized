import { useState } from 'react';
import { Box, Tabs, Tab } from '@mui/material';
import { DashboardPage } from './pages/DashboardPage';
import { NewsPage } from './pages/NewsPage';

type TabValue = 'dashboard' | 'news';

export default function App() {
  const [activeTab, setActiveTab] = useState<TabValue>('dashboard');

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <Tabs
        value={activeTab}
        onChange={(_, v) => setActiveTab(v as TabValue)}
        sx={{
          borderBottom: '1px solid',
          borderColor: 'divider',
          bgcolor: 'background.paper',
          mb: 2,
        }}
      >
        <Tab value="dashboard" label="Dashboard" />
        <Tab value="news" label="AI News" />
      </Tabs>

      {activeTab === 'dashboard' && <DashboardPage />}
      {activeTab === 'news' && <NewsPage />}
    </Box>
  );
}
