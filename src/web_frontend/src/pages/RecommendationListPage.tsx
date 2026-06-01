import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Table,
  Typography,
  Tag,
  Button,
  Space,
  Input,
  Card,
  message,
  Tabs,
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

const { Title, Paragraph, Text } = Typography;
const { Search } = Input;
type RecommendationStatusFilter = 'GENERATING' | 'PENDING' | 'PENDING,PROCESSING' | 'COMPLETED' | 'CANCELLED' | 'FAILED';

function RecommendationListPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialPage = Number(searchParams.get('page')) || 1;
  const initialPageSize = Number(searchParams.get('page_size')) || 10;
  const initialTab = searchParams.get('tab') || 'all';
  const initialMaterial = searchParams.get('material') || undefined;
  const [loading, setLoading] = useState(false);
  const [recommendations, setRecommendations] = useState<RecommendationSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(initialPage);
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [activeTab, setActiveTab] = useState<string>(initialTab);
  const [materialFilter, setMaterialFilter] = useState<string | undefined>(initialMaterial);
  const currentPageRef = useRef(currentPage);
  const pageSizeRef = useRef(pageSize);
  const activeTabRef = useRef(activeTab);
  const materialFilterRef = useRef(materialFilter);
  const fetchRecommendationsRef = useRef<() => void>(() => undefined);
  const fetchStatusCountsRef = useRef<() => void>(() => undefined);

  // Use ref instead of state to avoid closure issues
  const pollingIntervalRef = useRef<number | null>(null);

  // Track if there are any generating tasks for polling
  const [hasGeneratingTasks, setHasGeneratingTasks] = useState(false);

  const ensurePolling = useCallback((shouldPoll: boolean) => {
    if (shouldPoll) {
      setHasGeneratingTasks(true);
      if (!pollingIntervalRef.current) {
        const interval = window.setInterval(() => {
          fetchRecommendationsRef.current();
          fetchStatusCountsRef.current();
        }, 5000);
        pollingIntervalRef.current = interval;
      }
      return;
    }

    setHasGeneratingTasks(false);
    if (pollingIntervalRef.current) {
      window.clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }, []);

  const buildListSearch = useCallback(
    (overrides?: {
      page?: number;
      pageSize?: number;
      tab?: string;
      material?: string | null;
    }) => {
      const nextPage = overrides?.page ?? currentPage;
      const nextPageSize = overrides?.pageSize ?? pageSize;
      const nextTab = overrides?.tab ?? activeTab;
      const hasMaterialOverride = Object.prototype.hasOwnProperty.call(
        overrides ?? {},
        'material'
      );
      const nextMaterial = hasMaterialOverride
        ? overrides?.material || undefined
        : materialFilter;
      const params = new URLSearchParams();

      if (nextPage > 1) {
        params.set('page', String(nextPage));
      }
      if (nextPageSize !== 10) {
        params.set('page_size', String(nextPageSize));
      }
      if (nextTab !== 'all') {
        params.set('tab', nextTab);
      }
      if (nextMaterial) {
        params.set('material', nextMaterial);
      }

      const query = params.toString();
      return query ? `/recommendations?${query}` : '/recommendations';
    },
    [activeTab, currentPage, materialFilter, pageSize]
  );

  const navigateToListState = useCallback(
    (overrides?: {
      page?: number;
      pageSize?: number;
      tab?: string;
      material?: string | null;
    }) => {
      const path = buildListSearch(overrides);
      const paramsText = path.includes('?') ? path.slice(path.indexOf('?') + 1) : '';
      setSearchParams(paramsText ? new URLSearchParams(paramsText) : new URLSearchParams(), {
        replace: true,
      });
    },
    [buildListSearch, setSearchParams]
  );

  const renderMolarRatio = (molarRatio: string) => {
    const ratioParts = molarRatio.split(/\s*:\s*/).filter(Boolean);

    if (ratioParts.length === 0) {
      return molarRatio;
    }

    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          whiteSpace: 'nowrap',
          fontFamily: 'inherit',
          fontSize: 'inherit',
          fontWeight: 'inherit',
          lineHeight: 'inherit',
        }}
      >
        {ratioParts.map((part, index) => (
          <span
            key={`${part}-${index}`}
            style={{ display: 'inline-flex', alignItems: 'center' }}
          >
            <span>{part}</span>
            {index < ratioParts.length - 1 && (
              <span
                style={{
                  margin: '0 10px',
                  color: 'inherit',
                }}
              >
                :
              </span>
            )}
          </span>
        ))}
      </span>
    );
  };

  const renderFormulationDisplay = (formulation: FormulationData) => {
    const ratioDisplay = (
      <span
        style={{
          display: 'block',
          marginTop: 4,
          color: 'inherit',
          fontFamily: 'inherit',
          fontSize: 'inherit',
          fontWeight: 'inherit',
          lineHeight: 'inherit',
          whiteSpace: 'nowrap',
        }}
      >
        ({renderMolarRatio(formulation.molar_ratio)})
      </span>
    );

    if (formulation.HBD && formulation.HBA) {
      return (
        <>
          {formulation.HBD}
          <span style={{ margin: '0 6px', color: 'rgba(0, 0, 0, 0.45)' }}>:</span>
          {formulation.HBA}
          {ratioDisplay}
        </>
      );
    }

    if (formulation.components && formulation.components.length > 0) {
      return (
        <>
          {formulation.components.map((component, index) => (
            <span key={`${component.name}-${component.role}-${index}`}>
              {index > 0 && (
                <span style={{ margin: '0 6px', color: 'rgba(0, 0, 0, 0.45)' }}>+</span>
              )}
              {component.name}
            </span>
          ))}
          {ratioDisplay}
        </>
      );
    }

    return <>Unknown formulation {ratioDisplay}</>;
  };

  // Status counts for all tabs (always displayed)
  const [statusCounts, setStatusCounts] = useState<{
    all: number;
    generating: number;
    processing: number;
    pending: number;
    completed: number;
    failed: number;
  }>({
    all: 0,
    generating: 0,
    processing: 0,
    pending: 0,
    completed: 0,
    failed: 0,
  });

  useEffect(() => {
    currentPageRef.current = currentPage;
    pageSizeRef.current = pageSize;
    activeTabRef.current = activeTab;
    materialFilterRef.current = materialFilter;
  }, [activeTab, currentPage, materialFilter, pageSize]);

  // Fetch counts for all statuses (fast - single API call)
  const fetchStatusCounts = useCallback(async (): Promise<boolean> => {
    try {
      // Use new fast statistics API (single call, index only)
      const statsResp = await recommendationService.getStatistics({
        material: materialFilterRef.current,
      });

      setStatusCounts({
        all: statsResp.data.all,
        generating: statsResp.data.GENERATING,
        processing: statsResp.data.PROCESSING || 0,
        pending: statsResp.data.PENDING,
        completed: statsResp.data.COMPLETED,
        failed: (statsResp.data.FAILED || 0) + (statsResp.data.CANCELLED || 0),
      });

      const statusCountsNeedPolling =
        statsResp.data.GENERATING > 0 || (statsResp.data.PROCESSING || 0) > 0;
      if (statusCountsNeedPolling) {
        ensurePolling(true);
      }
      return statusCountsNeedPolling;
    } catch (error) {
      console.error('Failed to fetch status counts:', error);
      return false;
    }
  }, [ensurePolling]);

  // Determine status filter based on active tab
  const getStatusFilter = useCallback((): RecommendationStatusFilter | undefined => {
    switch (activeTabRef.current) {
      case 'generating':
        return 'GENERATING';
      case 'pending':
        return 'PENDING,PROCESSING';
      case 'completed':
        return 'COMPLETED';
      case 'failed':
        return 'FAILED';
      case 'all':
      default:
        return undefined;
    }
  }, []);

  const fetchRecommendations = useCallback(async () => {
    setLoading(true);
    try {
      const statusFilter = getStatusFilter();
      const response = await recommendationService.listRecommendations({
        status: statusFilter,
        material: materialFilterRef.current,
        page: currentPageRef.current,
        page_size: pageSizeRef.current,
      });
      setRecommendations(response.data.items);
      setTotal(response.data.pagination.total);

      const visibleItemsNeedPolling = response.data.items.some(
        (item) => item.status === 'GENERATING' || item.status === 'PROCESSING'
      );

      // Fetch status counts for tab badges
      const statusCountsNeedPolling = await fetchStatusCounts();
      ensurePolling(visibleItemsNeedPolling || statusCountsNeedPolling);
    } catch (error) {
      console.error('Failed to fetch recommendations:', error);
      message.error('获取推荐列表失败');
    } finally {
      setLoading(false);
    }
  }, [getStatusFilter, fetchStatusCounts, ensurePolling]);

  useEffect(() => {
    fetchRecommendationsRef.current = fetchRecommendations;
  }, [fetchRecommendations]);

  useEffect(() => {
    fetchStatusCountsRef.current = fetchStatusCounts;
  }, [fetchStatusCounts]);

  // Initial fetch and when dependencies change. Polling reads the same refs, so
  // in-progress generation updates keep the visible page/filter stable.
  useEffect(() => {
    fetchRecommendationsRef.current();
  }, [currentPage, pageSize, activeTab, materialFilter]);

  useEffect(() => {
    const pageFromUrl = Number(searchParams.get('page')) || 1;
    const pageSizeFromUrl = Number(searchParams.get('page_size')) || 10;
    const tabFromUrl = searchParams.get('tab') || 'all';
    const materialFromUrl = searchParams.get('material') || undefined;

    setCurrentPage((prev) => (prev === pageFromUrl ? prev : pageFromUrl));
    currentPageRef.current = pageFromUrl;
    setPageSize((prev) => (prev === pageSizeFromUrl ? prev : pageSizeFromUrl));
    pageSizeRef.current = pageSizeFromUrl;
    setActiveTab((prev) => (prev === tabFromUrl ? prev : tabFromUrl));
    activeTabRef.current = tabFromUrl;
    setMaterialFilter((prev) => (prev === materialFromUrl ? prev : materialFromUrl));
    materialFilterRef.current = materialFromUrl;
  }, [searchParams]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        window.clearInterval(pollingIntervalRef.current);
      }
    };
  }, []);

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
            {renderFormulationDisplay(formulation)}
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
      render: (_: unknown, record: RecommendationSummary) => {
        const hasExperimentResult = record.performance_score !== null && record.performance_score !== undefined;
        const canSubmitFeedback = record.status === 'PENDING';
        const canUpdateFeedback = record.status === 'COMPLETED' || hasExperimentResult;
        const canOpenFeedback = canSubmitFeedback || canUpdateFeedback;

        return (
          <Space size="small">
            <Button
              type="link"
              icon={<EyeOutlined />}
              onClick={() =>
                navigate(`/recommendations/${record.recommendation_id}`, {
                  state: {
                    from: buildListSearch(),
                  },
                })
              }
              disabled={record.status === 'GENERATING' || record.status === 'PROCESSING'}
            >
              详情
            </Button>
            {canOpenFeedback && (
              <Button
                type="link"
                icon={<ExperimentOutlined />}
                onClick={() =>
                  navigate(`/feedback/${record.recommendation_id}`, {
                    state: {
                      from: buildListSearch(),
                      detailFrom: `/recommendations/${record.recommendation_id}`,
                    },
                  })
                }
              >
                {canUpdateFeedback ? '更新' : '反馈'}
              </Button>
            )}
            {record.status === 'GENERATING' && (
              <Text type="secondary" style={{ fontSize: '12px' }}>
                生成中...
              </Text>
            )}
            {record.status === 'PROCESSING' && (
              <Button
                type="link"
                icon={<LoadingOutlined spin />}
                onClick={() =>
                  navigate(`/feedback/${record.recommendation_id}`, {
                    state: {
                      from: buildListSearch(),
                      detailFrom: `/recommendations/${record.recommendation_id}`,
                    },
                  })
                }
              >
                进度
              </Button>
            )}
          </Space>
        );
      },
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
          <ClockCircleOutlined /> 待实验 ({statusCounts.pending + statusCounts.processing})
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
      <Title level={2}>RECOMMENDATION LIST</Title>
      <Paragraph>
        View all recommended DES formulas and filter by status and materials. The tasks in the recipe generation process will be automatically refreshed.
      </Paragraph>

      {/* Alert for GENERATING tasks */}
      {hasGeneratingTasks && (
        <Alert
          message="Generating formula"
          description="The formula is being generated in the background. The list will automatically refresh every 5 seconds. Please wait patiently..."
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
          <span>Select Mateiral:</span>
          <Search
            placeholder="Type material name"
            allowClear
            style={{ width: 200 }}
            value={materialFilter}
            onChange={(e) => {
              const value = e.target.value;
              if (!value) {
                setMaterialFilter(undefined);
                materialFilterRef.current = undefined;
                setCurrentPage(1);
                currentPageRef.current = 1;
                navigateToListState({ page: 1, material: null });
              }
            }}
            onSearch={(value) => {
              const nextMaterial = value || undefined;
              setMaterialFilter(nextMaterial);
              materialFilterRef.current = nextMaterial;
              setCurrentPage(1);
              currentPageRef.current = 1;
              navigateToListState({ page: 1, material: nextMaterial });
            }}
          />

          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              setMaterialFilter(undefined);
              materialFilterRef.current = undefined;
              setCurrentPage(1);
              currentPageRef.current = 1;
              navigateToListState({ page: 1, material: null });
              fetchRecommendations();
            }}
          >
            RESET
          </Button>

          <Button
            type="primary"
            icon={<ReloadOutlined />}
            onClick={fetchRecommendations}
            loading={loading}
          >
            REFRESH
          </Button>

          {hasGeneratingTasks && (
            <Tag color="blue" icon={<SyncOutlined spin />}>
              Auto-refreshing
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
            activeTabRef.current = key;
            setCurrentPage(1);
            currentPageRef.current = 1;
            navigateToListState({ page: 1, tab: key });
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
              currentPageRef.current = page;
              setPageSize(size);
              pageSizeRef.current = size;
              navigateToListState({ page, pageSize: size });
            },
          }}
          locale={{
            emptyText:
              activeTab === 'generating'
                ? 'No tasks are currently being generated'
                : activeTab === 'pending'
                ? 'No formula await being experimented'
                : activeTab === 'completed'
                ? 'No formula has been experimentally tested so far'
                : activeTab === 'failed'
                ? 'No failed task has been recorded so far'
                : 'No recommendation formula available currently',
          }}
        />
      </Card>
    </div>
  );
}

export default RecommendationListPage;
