import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { Layout, Menu, Typography } from 'antd';
import {
  HomeOutlined,
  ExperimentOutlined,
  UnorderedListOutlined,
  BarChartOutlined,
  DatabaseOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import './App.css';

// Import pages (will be created)
import TaskSubmissionPage from './pages/TaskSubmissionPage';
import RecommendationListPage from './pages/RecommendationListPage';
import RecommendationDetailPage from './pages/RecommendationDetailPage';
import FeedbackPage from './pages/FeedbackPage';
import StatisticsPage from './pages/StatisticsPage';
import MemoriesPage from './pages/MemoriesPage';

const { Header, Sider, Content } = Layout;
const { Title } = Typography;

// Menu items configuration
type MenuItem = Required<MenuProps>['items'][number];

const menuItems: MenuItem[] = [
  {
    key: '/',
    icon: <HomeOutlined />,
    label: <Link to="/">任务提交</Link>,
  },
  {
    key: '/recommendations',
    icon: <UnorderedListOutlined />,
    label: <Link to="/recommendations">推荐列表</Link>,
  },
  {
    key: '/memories',
    icon: <DatabaseOutlined />,
    label: <Link to="/memories">记忆库</Link>,
  },
  {
    key: '/statistics',
    icon: <BarChartOutlined />,
    label: <Link to="/statistics">统计仪表板</Link>,
  },
];

function AppLayout() {
  const location = useLocation();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        background: '#001529'
      }}>
        <ExperimentOutlined style={{ fontSize: '24px', color: '#fff', marginRight: '16px' }} />
        <Title level={3} style={{ color: '#fff', margin: 0 }}>
          DES配方推荐系统
        </Title>
      </Header>
      <Layout>
        <Sider width={200} style={{ background: '#fff' }}>
          <Menu
            mode="inline"
            selectedKeys={[location.pathname]}
            style={{ height: '100%', borderRight: 0 }}
            items={menuItems}
          />
        </Sider>
        <Layout style={{ padding: '24px' }}>
          <Content
            style={{
              padding: 24,
              margin: 0,
              minHeight: 280,
              background: '#fff',
              borderRadius: '8px',
            }}
          >
            <Routes>
              <Route path="/" element={<TaskSubmissionPage />} />
              <Route path="/recommendations" element={<RecommendationListPage />} />
              <Route path="/recommendations/:id" element={<RecommendationDetailPage />} />
              <Route path="/feedback/:id" element={<FeedbackPage />} />
              <Route path="/memories" element={<MemoriesPage />} />
              <Route path="/statistics" element={<StatisticsPage />} />
            </Routes>
          </Content>
        </Layout>
      </Layout>
    </Layout>
  );
}

function App() {
  return (
    <Router>
      <AppLayout />
    </Router>
  );
}

export default App;
