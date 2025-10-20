import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Table,
  Typography,
  Tag,
  Button,
  Space,
  Select,
  Input,
  Card,
  message,
  Tabs,
  Progress,
  Alert,
  Spin,
} from 'antd';
import {
  EyeOutlined,
  ExperimentOutlined,
  ReloadOutlined,
  SyncOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { recommendationService } from '../services';
import type { RecommendationSummary } from '../types';
import type { FormulationData } from '../types/formulation';
import { getFormulationDisplayString } from '../utils/formulationUtils';

const { Title, Paragraph, Text } = Typography;
const { Search } = Input;

function RecommendationListPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [recommendations, setRecommendations] = useState<RecommendationSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [activeTab, setActiveTab] = useState<string>('all');
  const [materialFilter, setMaterialFilter] = useState<string | undefined>(undefined);
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null);

  // Track if there are any generating tasks for polling
  const [hasGeneratingTasks, setHasGeneratingTasks] = useState(false);

  // Status counts for all tabs (always displayed)
  const [statusCounts, setStatusCounts] = useState<{
    all: number;
    generating: number;
    pending: number;
    completed: number;
    failed: number;
  }>({
    all: 0,
    generating: 0,
    pending: 0,
    completed: 0,
    failed: 0,
  });

  // Fetch counts for all statuses (fast - single API call)
  const fetchStatusCounts = useCallback(async () => {
    try {
      // Use new fast statistics API (single call, index only)
      const statsResp = await recommendationService.getStatistics({
        material: materialFilter,
      });

      setStatusCounts({
        all: statsResp.data.all,
        generating: statsResp.data.GENERATING,
        pending: statsResp.data.PENDING,
        completed: statsResp.data.COMPLETED,
        failed: statsResp.data.FAILED,
      });

      // Check if need to start/stop polling
      if (statsResp.data.GENERATING > 0) {
        setHasGeneratingTasks(true);
        if (!pollingInterval) {
          const interval = setInterval(() => {
            fetchRecommendations();
            fetchStatusCounts();
          }, 5000);
          setPollingInterval(interval);
        }
      } else {
        setHasGeneratingTasks(false);
        if (pollingInterval) {
          clearInterval(pollingInterval);
          setPollingInterval(null);
        }
      }
    } catch (error) {
      console.error('Failed to fetch status counts:', error);
    }
  }, [materialFilter, pollingInterval]);

  // Determine status filter based on active tab
  const getStatusFilter = useCallback(() => {
    switch (activeTab) {
      case 'generating':
        return 'GENERATING';
      case 'pending':
        return 'PENDING';
      case 'completed':
        return 'COMPLETED';
      case 'failed':
        return 'FAILED';
      case 'all':
      default:
        return undefined;
    }
  }, [activeTab]);

  const fetchRecommendations = useCallback(async () => {
    setLoading(true);
    try {
      const statusFilter = getStatusFilter();
      const response = await recommendationService.listRecommendations({
        status: statusFilter as any,
        material: materialFilter,
        page: currentPage,
        page_size: pageSize,
      });
      setRecommendations(response.data.items);
      setTotal(response.data.pagination.total);

      // Fetch status counts for tab badges
      await fetchStatusCounts();
    } catch (error) {
      console.error('Failed to fetch recommendations:', error);
      message.error('获取推荐列表失败');
    } finally {
      setLoading(false);
    }
  }, [currentPage, pageSize, materialFilter, getStatusFilter, fetchStatusCounts]);

  // Initial fetch and when dependencies change
  useEffect(() => {
    fetchRecommendations();
  }, [currentPage, pageSize, activeTab, materialFilter]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, [pollingInterval]);

  const columns = [
    {
      title: '推荐ID',
      dataIndex: 'recommendation_id',
      key: 'recommendation_id',
      width: 120,
      render: (id: string) => (
        <Typography.Text code>{id.slice(0, 8)}</Typography.Text>
      ),
    },
    {
      title: '配方',
      dataIndex: 'formulation',
      key: 'formulation',
      render: (formulation: FormulationData, record: RecommendationSummary) => {
        // If GENERATING, show placeholder
        if (record.status === 'GENERATING') {
          return (
            <Space>
              <Spin indicator={<LoadingOutlined style={{ fontSize: 16 }} spin />} />
              <Text type="secondary">生成中...</Text>
            </Space>
          );
        }
        return (
          <Typography.Text strong>
            {getFormulationDisplayString(formulation)}
          </Typography.Text>
        );
      },
    },
    {
      title: '目标材料',
      dataIndex: 'target_material',
      key: 'target_material',
      render: (material: string) => <Tag color="cyan">{material}</Tag>,
    },
    {
      title: '目标温度',
      dataIndex: 'target_temperature',
      key: 'target_temperature',
      render: (temp: number) => `${temp}°C`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const colorMap: Record<string, string> = {
          GENERATING: 'blue',
          PENDING: 'orange',
          PROCESSING: 'cyan',
          COMPLETED: 'green',
          CANCELLED: 'red',
          FAILED: 'red',
        };
        const labelMap: Record<string, string> = {
          GENERATING: '生成中',
          PENDING: '待实验',
          PROCESSING: '处理中',
          COMPLETED: '已完成',
          CANCELLED: '已取消',
          FAILED: '生成失败',
        };
        const iconMap: Record<string, React.ReactNode> = {
          GENERATING: <SyncOutlined spin />,
          PENDING: <ClockCircleOutlined />,
          PROCESSING: <LoadingOutlined spin />,
          COMPLETED: <CheckCircleOutlined />,
          CANCELLED: <CloseCircleOutlined />,
          FAILED: <ExclamationCircleOutlined />,
        };
        return (
          <Tag color={colorMap[status]} icon={iconMap[status]}>
            {labelMap[status]}
          </Tag>
        );
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right' as const,
      width: 180,
      render: (_: unknown, record: RecommendationSummary) => (
        <Space size="small">
          <Button
            type="link"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/recommendations/${record.recommendation_id}`)}
            disabled={record.status === 'GENERATING' || record.status === 'PROCESSING'}
          >
            详情
          </Button>
          {record.status === 'PENDING' && (
            <Button
              type="link"
              icon={<ExperimentOutlined />}
              onClick={() => navigate(`/feedback/${record.recommendation_id}`)}
            >
              反馈
            </Button>
          )}
          {record.status === 'COMPLETED' && (
            <Button
              type="link"
              icon={<ExperimentOutlined />}
              onClick={() => navigate(`/feedback/${record.recommendation_id}`)}
            >
              更新
            </Button>
          )}
          {record.status === 'GENERATING' && (
            <Text type="secondary" style={{ fontSize: '12px' }}>
              生成中...
            </Text>
          )}
          {record.status === 'PROCESSING' && (
            <Text type="secondary" style={{ fontSize: '12px' }}>
              <LoadingOutlined spin /> 处理中...
            </Text>
          )}
        </Space>
      ),
    },
  ];

  // Tab items configuration - always show counts from statusCounts
  const tabItems = [
    {
      key: 'all',
      label: `全部 (${statusCounts.all})`,
      icon: null,
    },
    {
      key: 'generating',
      label: (
        <span>
          <SyncOutlined spin={statusCounts.generating > 0} /> 生成中 ({statusCounts.generating})
        </span>
      ),
    },
    {
      key: 'pending',
      label: (
        <span>
          <ClockCircleOutlined /> 待实验 ({statusCounts.pending})
        </span>
      ),
    },
    {
      key: 'completed',
      label: (
        <span>
          <CheckCircleOutlined /> 已完成 ({statusCounts.completed})
        </span>
      ),
    },
    {
      key: 'failed',
      label: (
        <span>
          <ExclamationCircleOutlined /> 失败 ({statusCounts.failed})
        </span>
      ),
    },
  ];

  return (
    <div>
      <Title level={2}>推荐列表</Title>
      <Paragraph>
        查看所有DES配方推荐，可按状态和材料筛选。配方生成中的任务会自动刷新。
      </Paragraph>

      {/* Alert for GENERATING tasks */}
      {hasGeneratingTasks && (
        <Alert
          message="配方生成中"
          description="有配方正在后台生成，列表将每5秒自动刷新。请耐心等待..."
          type="info"
          icon={<SyncOutlined spin />}
          showIcon
          closable
          style={{ marginBottom: 16 }}
        />
      )}

      {/* Filter Card */}
      <Card style={{ marginBottom: 16 }}>
        <Space size="middle" wrap>
          <span>材料筛选:</span>
          <Search
            placeholder="输入材料名称"
            allowClear
            style={{ width: 200 }}
            value={materialFilter}
            onChange={(e) => {
              const value = e.target.value;
              if (!value) {
                setMaterialFilter(undefined);
                setCurrentPage(1);
              }
            }}
            onSearch={(value) => {
              setMaterialFilter(value || undefined);
              setCurrentPage(1);
            }}
          />

          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              setMaterialFilter(undefined);
              setCurrentPage(1);
              fetchRecommendations();
            }}
          >
            重置
          </Button>

          <Button
            type="primary"
            icon={<ReloadOutlined />}
            onClick={fetchRecommendations}
            loading={loading}
          >
            手动刷新
          </Button>

          {pollingInterval && (
            <Tag color="blue" icon={<SyncOutlined spin />}>
              自动刷新中
            </Tag>
          )}
        </Space>
      </Card>

      {/* Tabs for status filtering */}
      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={(key) => {
            setActiveTab(key);
            setCurrentPage(1);
          }}
          items={tabItems}
          style={{ marginBottom: 16 }}
        />

        <Table
          columns={columns}
          dataSource={recommendations}
          rowKey="recommendation_id"
          loading={loading}
          scroll={{ x: 1200 }}
          pagination={{
            current: currentPage,
            pageSize: pageSize,
            total: total,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (page, size) => {
              setCurrentPage(page);
              setPageSize(size);
            },
          }}
          locale={{
            emptyText:
              activeTab === 'generating'
                ? '暂无生成中的任务'
                : activeTab === 'pending'
                ? '暂无待实验的推荐'
                : activeTab === 'completed'
                ? '暂无已完成的推荐'
                : activeTab === 'failed'
                ? '暂无失败的任务'
                : '暂无推荐数据',
          }}
        />
      </Card>
    </div>
  );
}

export default RecommendationListPage;
