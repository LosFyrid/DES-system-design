import { useState, useEffect } from 'react';
import {
  Card,
  Row,
  Col,
  Statistic,
  Typography,
  Table,
  Tag,
  DatePicker,
  Button,
  Space,
  Spin,
} from 'antd';
import {
  ExperimentOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  TrophyOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { statisticsService } from '../services';
import type {
  LeachingEfficiencyByElementStats,
  StatisticsData,
  PerformanceTrendPoint,
} from '../types';

const { Title, Paragraph } = Typography;
const { RangePicker } = DatePicker;

function StatisticsPage() {
  const [loading, setLoading] = useState(true);
  const [statistics, setStatistics] = useState<StatisticsData | null>(null);
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>([
    dayjs().subtract(30, 'day'),
    dayjs(),
  ]);
  const [trendData, setTrendData] = useState<PerformanceTrendPoint[]>([]);
  const [trendLoading, setTrendLoading] = useState(false);

  const fetchStatistics = async () => {
    setLoading(true);
    try {
      const response = await statisticsService.getStatistics();
      setStatistics(response.data);
    } catch (error) {
      console.error('Failed to fetch statistics:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchTrend = async () => {
    setTrendLoading(true);
    try {
      const response = await statisticsService.getPerformanceTrend({
        start_date: dateRange[0].format('YYYY-MM-DD'),
        end_date: dateRange[1].format('YYYY-MM-DD'),
      });
      setTrendData(response.data);
    } catch (error) {
      console.error('Failed to fetch performance trend:', error);
    } finally {
      setTrendLoading(false);
    }
  };

  useEffect(() => {
    fetchStatistics();
    fetchTrend();
  }, []);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!statistics) {
    return <div>No statistics available</div>;
  }

  const trendColumns = [
    {
      title: 'Data',
      dataIndex: 'date',
      key: 'date',
      render: (date: string) => dayjs(date).format('YYYY-MM-DD'),
    },
    {
      title: 'Experiment Count',
      dataIndex: 'experiment_count',
      key: 'experiment_count',
      sorter: (a: PerformanceTrendPoint, b: PerformanceTrendPoint) =>
        a.experiment_count - b.experiment_count,
    },
    {
      title: 'Leaching Efficiency Average (%)',
      dataIndex: 'max_leaching_efficiency_mean',
      key: 'max_leaching_efficiency_mean',
      render: (val?: number) =>
        val !== undefined && val !== null ? <Tag color="blue">{val.toFixed(2)}%</Tag> : <Tag>--</Tag>,
      sorter: (a: PerformanceTrendPoint, b: PerformanceTrendPoint) =>
        (a.max_leaching_efficiency_mean || 0) - (b.max_leaching_efficiency_mean || 0),
    },
    {
      title: 'Leaching Efficiency Median (%)',
      dataIndex: 'max_leaching_efficiency_median',
      key: 'max_leaching_efficiency_median',
      render: (val?: number) =>
        val !== undefined && val !== null ? <Tag>{val.toFixed(2)}%</Tag> : <Tag>--</Tag>,
      sorter: (a: PerformanceTrendPoint, b: PerformanceTrendPoint) =>
        (a.max_leaching_efficiency_median || 0) - (b.max_leaching_efficiency_median || 0),
    },
    {
      title: 'Liquid Formation Rate(%)',
      dataIndex: 'liquid_formation_rate',
      key: 'liquid_formation_rate',
      render: (val: number) => `${(val * 100).toFixed(1)}%`,
      sorter: (a: PerformanceTrendPoint, b: PerformanceTrendPoint) =>
        a.liquid_formation_rate - b.liquid_formation_rate,
    },
  ];

  const topFormulationColumns = [
    {
      title: 'Rank',
      key: 'rank',
      render: (_: unknown, __: unknown, index: number) => (
        <Tag color={index < 3 ? 'gold' : 'default'}>{index + 1}</Tag>
      ),
    },
    {
      title: 'Formula',
      dataIndex: 'formulation',
      key: 'formulation',
      render: (text: string) => <Typography.Text strong>{text}</Typography.Text>,
    },
    {
      title: 'Average Leaching Efficiency (%)',
      dataIndex: 'avg_max_leaching_efficiency',
      key: 'avg_max_leaching_efficiency',
      render: (val?: number) =>
        val !== undefined && val !== null ? <Tag color="blue">{val.toFixed(2)}%</Tag> : <Tag>--</Tag>,
    },
    {
      title: 'Experiment Count',
      dataIndex: 'success_count',
      key: 'success_count',
    },
  ];

  const leachingByElementColumns = [
    {
      title: 'Element / Material',
      dataIndex: 'element',
      key: 'element',
      render: (text: string) => <Tag color="cyan">{text}</Tag>,
    },
    {
      title: 'Measurements',
      dataIndex: 'measurement_count',
      key: 'measurement_count',
      sorter: (a: LeachingEfficiencyByElementStats, b: LeachingEfficiencyByElementStats) =>
        a.measurement_count - b.measurement_count,
    },
    {
      title: 'Experiments',
      dataIndex: 'experiment_count',
      key: 'experiment_count',
      sorter: (a: LeachingEfficiencyByElementStats, b: LeachingEfficiencyByElementStats) =>
        a.experiment_count - b.experiment_count,
    },
    {
      title: 'Mean Max (%)',
      dataIndex: 'max_leaching_efficiency_mean',
      key: 'max_leaching_efficiency_mean',
      render: (v?: number) =>
        v != null ? <Tag color="blue">{v.toFixed(2)}%</Tag> : <Tag>--</Tag>,
      sorter: (a: LeachingEfficiencyByElementStats, b: LeachingEfficiencyByElementStats) =>
        (a.max_leaching_efficiency_mean || 0) - (b.max_leaching_efficiency_mean || 0),
    },
    {
      title: 'Median Max (%)',
      dataIndex: 'max_leaching_efficiency_median',
      key: 'max_leaching_efficiency_median',
      render: (v?: number) => (v != null ? `${v.toFixed(2)}%` : '--'),
      sorter: (a: LeachingEfficiencyByElementStats, b: LeachingEfficiencyByElementStats) =>
        (a.max_leaching_efficiency_median || 0) - (b.max_leaching_efficiency_median || 0),
    },
    {
      title: 'P90 Max (%)',
      dataIndex: 'max_leaching_efficiency_p90',
      key: 'max_leaching_efficiency_p90',
      render: (v?: number) => (v != null ? `${v.toFixed(2)}%` : '--'),
      sorter: (a: LeachingEfficiencyByElementStats, b: LeachingEfficiencyByElementStats) =>
        (a.max_leaching_efficiency_p90 || 0) - (b.max_leaching_efficiency_p90 || 0),
    },
    {
      title: 'Mean Latest (%)',
      dataIndex: 'latest_leaching_efficiency_mean',
      key: 'latest_leaching_efficiency_mean',
      render: (v?: number) => (v != null ? `${v.toFixed(2)}%` : '--'),
      sorter: (a: LeachingEfficiencyByElementStats, b: LeachingEfficiencyByElementStats) =>
        (a.latest_leaching_efficiency_mean || 0) - (b.latest_leaching_efficiency_mean || 0),
    },
  ];

  const targetMaterialColumns = [
    { title: 'Target Material', dataIndex: 'target_material', key: 'target_material' },
    { title: '实验数', dataIndex: 'experiments_total', key: 'experiments_total', sorter: (a: any, b: any) => a.experiments_total - b.experiments_total },
    { title: '形成率', dataIndex: 'liquid_formation_rate', key: 'liquid_formation_rate', render: (v: number) => `${(v * 100).toFixed(1)}%`, sorter: (a: any, b: any) => a.liquid_formation_rate - b.liquid_formation_rate },
    { title: 'Leaching Efficiency Average (%)', dataIndex: 'max_leaching_efficiency_mean', key: 'max_leaching_efficiency_mean', render: (v?: number) => v != null ? v.toFixed(2) : '--', sorter: (a: any, b: any) => (a.max_leaching_efficiency_mean || 0) - (b.max_leaching_efficiency_mean || 0) },
    { title: 'Leaching Efficiency Median (%)', dataIndex: 'max_leaching_efficiency_median', key: 'max_leaching_efficiency_median', render: (v?: number) => v != null ? v.toFixed(2) : '--', sorter: (a: any, b: any) => (a.max_leaching_efficiency_median || 0) - (b.max_leaching_efficiency_median || 0) },
    { title: 'Leaching Efficiency Max P90 (%)', dataIndex: 'max_leaching_efficiency_p90', key: 'max_leaching_efficiency_p90', render: (v?: number) => v != null ? v.toFixed(2) : '--', sorter: (a: any, b: any) => (a.max_leaching_efficiency_p90 || 0) - (b.max_leaching_efficiency_p90 || 0) },
    { title: '平均测量条数', dataIndex: 'measurement_rows_mean', key: 'measurement_rows_mean', render: (v?: number) => v != null ? v.toFixed(2) : '--', sorter: (a: any, b: any) => (a.measurement_rows_mean || 0) - (b.measurement_rows_mean || 0) },
  ];

  return (
    <div>
      <Title level={2}>STATISTICAL BOARD</Title>
      <Paragraph>
        System Performance Overview and Trend Analysis
      </Paragraph>

      {/* Summary Statistics */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Total Recommendation"
              value={statistics.summary.total_recommendations}
              prefix={<ExperimentOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="To Be Tested"
              value={statistics.summary.pending_experiments}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Completed"
              value={statistics.summary.completed_experiments}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="Cancelled"
              value={statistics.summary.cancelled}
              prefix={<CloseCircleOutlined />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12}>
          <Card>
            <Statistic
              title="Liquid Formation Success Rate"
              value={(statistics.summary.liquid_formation_rate * 100).toFixed(1)}
              suffix="%"
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12}>
          <Card>
            <Statistic
              title="Leaching Efficiency Average"
              value={
                statistics.summary.max_leaching_efficiency_mean !== undefined &&
                statistics.summary.max_leaching_efficiency_mean !== null
                  ? statistics.summary.max_leaching_efficiency_mean.toFixed(2)
                  : '--'
              }
              suffix="%"
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12}>
          <Card>
            <Statistic
              title="Median Leaching Efficiency"
              value={
                statistics.summary.max_leaching_efficiency_median !== undefined &&
                statistics.summary.max_leaching_efficiency_median !== null
                  ? statistics.summary.max_leaching_efficiency_median.toFixed(2)
                  : '--'
              }
              suffix="%"
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12}>
          <Card>
            <Statistic
              title="Measurement Strips Average"
              value={
                statistics.summary.measurement_rows_mean !== undefined &&
                statistics.summary.measurement_rows_mean !== null
                  ? statistics.summary.measurement_rows_mean.toFixed(2)
                  : '--'
              }
            />
          </Card>
        </Col>
      </Row>

      {/* By Material and By Status */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={12}>
          <Card title="By Material Distribution" bordered>
            {Object.entries(statistics.by_material)
              .sort(([, a], [, b]) => b - a)
              .map(([material, count]) => (
                <div
                  key={material}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    marginBottom: 12,
                  }}
                >
                  <Tag color="cyan">{material}</Tag>
                  <Typography.Text strong>{count} Recommendation</Typography.Text>
                </div>
              ))}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="By Status Distribution" bordered>
            {Object.entries(statistics.by_status).map(([status, count]) => {
              const colorMap: Record<string, string> = {
                PENDING: 'orange',
                COMPLETED: 'green',
                CANCELLED: 'red',
              };
              const labelMap: Record<string, string> = {
                PENDING: 'To be tested',
                COMPLETED: 'Completed',
                CANCELLED: 'Cancelled',
              };
              return (
                <div
                  key={status}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    marginBottom: 12,
                  }}
                >
                  <Tag color={colorMap[status]}>{labelMap[status]}</Tag>
                  <Typography.Text strong>{count} Recommendation</Typography.Text>
                </div>
              );
            })}
          </Card>
        </Col>
      </Row>

      {/* Target material stats */}
      <Card
        title="Leaching Efficiency By Element / Material"
        style={{ marginBottom: 24 }}
      >
        <Table
          columns={leachingByElementColumns}
          dataSource={statistics.leaching_efficiency_by_element || []}
          rowKey="element"
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Card
        title="By Target Material"
        style={{ marginBottom: 24 }}
      >
        <Table
          columns={targetMaterialColumns}
          dataSource={statistics.target_material_stats || []}
          rowKey="target_material"
          pagination={{ pageSize: 10 }}
        />
      </Card>

      {/* Performance Trend */}
      <Card
        title="Leaching Trend"
        extra={
          <Space>
            <RangePicker
              value={dateRange}
              onChange={(dates) => {
                if (dates && dates[0] && dates[1]) {
                  setDateRange([dates[0], dates[1]]);
                }
              }}
            />
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              onClick={fetchTrend}
              loading={trendLoading}
            >
              刷新
            </Button>
          </Space>
        }
        style={{ marginBottom: 24 }}
      >
        <Table
          columns={trendColumns}
          dataSource={trendData}
          rowKey="date"
          loading={trendLoading}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      {/* Top Formulations */}
      <Card
        title={
          <Space>
            <TrophyOutlined style={{ color: '#faad14' }} />
            <span>Optimial Formula Top 10</span>
          </Space>
        }
      >
        <Table
          columns={topFormulationColumns}
          dataSource={statistics.top_formulations}
          rowKey="formulation"
          pagination={false}
        />
      </Card>
    </div>
  );
}

export default StatisticsPage;
