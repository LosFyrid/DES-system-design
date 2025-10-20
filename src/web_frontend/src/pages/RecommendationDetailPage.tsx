import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card,
  Descriptions,
  Tag,
  Button,
  Space,
  Typography,
  Divider,
  Alert,
  Spin,
  Progress,
  List,
} from 'antd';
import {
  ArrowLeftOutlined,
  ExperimentOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { recommendationService } from '../services';
import type { RecommendationDetail } from '../types';
import { getFormulationDisplayString } from '../utils/formulationUtils';

const { Title, Paragraph, Text } = Typography;

function RecommendationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<RecommendationDetail | null>(null);

  useEffect(() => {
    if (!id) return;

    const fetchDetail = async () => {
      setLoading(true);
      try {
        const response = await recommendationService.getRecommendationDetail(id);
        setDetail(response.data);
      } catch (error) {
        console.error('Failed to fetch recommendation detail:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchDetail();
  }, [id]);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!detail) {
    return (
      <Alert
        message="推荐不存在"
        description="未找到该推荐信息"
        type="error"
        showIcon
      />
    );
  }

  const statusColorMap: Record<string, string> = {
    GENERATING: 'blue',
    PENDING: 'orange',
    COMPLETED: 'green',
    CANCELLED: 'red',
    FAILED: 'red',
  };

  const statusLabelMap: Record<string, string> = {
    GENERATING: '生成中',
    PENDING: '待实验',
    COMPLETED: '已完成',
    CANCELLED: '已取消',
    FAILED: '生成失败',
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/recommendations')}
        >
          返回列表
        </Button>
        {detail.status === 'PENDING' && (
          <Button
            type="primary"
            icon={<ExperimentOutlined />}
            onClick={() => navigate(`/feedback/${detail.recommendation_id}`)}
          >
            提交实验反馈
          </Button>
        )}
      </Space>

      {/* Special alert for GENERATING status */}
      {detail.status === 'GENERATING' && (
        <Alert
          message="配方生成中"
          description="AI Agent 正在后台分析任务并生成配方推荐，这可能需要几分钟时间。请稍后刷新页面查看结果。"
          type="info"
          showIcon
          icon={<Spin indicator={<LoadingOutlined style={{ fontSize: 24 }} spin />} />}
          style={{ marginBottom: 16 }}
        />
      )}

      {/* Special alert for FAILED status */}
      {detail.status === 'FAILED' && (
        <Alert
          message="配方生成失败"
          description={detail.reasoning || "配方生成过程中出现错误，请查看下方详情或联系管理员。"}
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <Card>
        <Title level={2}>
          {detail.status === 'GENERATING'
            ? '配方生成中...'
            : getFormulationDisplayString(detail.formulation)}
        </Title>
        <Tag color={statusColorMap[detail.status]} style={{ marginBottom: 16 }}>
          {statusLabelMap[detail.status]}
        </Tag>

        <Descriptions bordered column={2}>
          <Descriptions.Item label="推荐ID" span={2}>
            <Text code>{detail.recommendation_id}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="目标材料">
            <Tag color="cyan">{detail.task.target_material}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="目标温度">
            {detail.task.target_temperature}°C
          </Descriptions.Item>

          {/* Binary formulation */}
          {detail.formulation.HBD && detail.formulation.HBA && (
            <>
              <Descriptions.Item label="HBD (氢键供体)">
                <Tag color="blue">{detail.formulation.HBD}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="HBA (氢键受体)">
                <Tag color="green">{detail.formulation.HBA}</Tag>
              </Descriptions.Item>
            </>
          )}

          {/* Multi-component formulation */}
          {detail.formulation.components && detail.formulation.components.length > 0 && (
            <Descriptions.Item label="配方组分" span={2}>
              <List
                size="small"
                dataSource={detail.formulation.components}
                renderItem={(component, index) => (
                  <List.Item>
                    <Space direction="vertical" size="small" style={{ width: '100%' }}>
                      <Text strong>
                        [{index + 1}] {component.name}
                      </Text>
                      <Text type="secondary">
                        角色: <Tag color="blue">{component.role}</Tag>
                      </Text>
                      {component.function && (
                        <Text type="secondary" style={{ fontSize: '12px' }}>
                          功能: {component.function}
                        </Text>
                      )}
                    </Space>
                  </List.Item>
                )}
              />
            </Descriptions.Item>
          )}

          <Descriptions.Item label="摩尔比">
            <Tag color="purple">{detail.formulation.molar_ratio}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="组分数量">
            {detail.formulation.num_components ||
             (detail.formulation.components ? detail.formulation.components.length : 2)}
          </Descriptions.Item>
          <Descriptions.Item label="置信度" span={2}>
            <Progress
              percent={Math.round(detail.confidence * 100)}
              size="small"
              style={{ width: 200 }}
            />
          </Descriptions.Item>
          <Descriptions.Item label="创建时间" span={2}>
            {dayjs(detail.created_at).format('YYYY-MM-DD HH:mm:ss')}
          </Descriptions.Item>
          {detail.updated_at && (
            <Descriptions.Item label="更新时间" span={2}>
              {dayjs(detail.updated_at).format('YYYY-MM-DD HH:mm:ss')}
            </Descriptions.Item>
          )}
        </Descriptions>

        <Divider orientation="left">推理过程</Divider>
        <Card type="inner">
          <Paragraph style={{ whiteSpace: 'pre-wrap' }}>
            {detail.reasoning}
          </Paragraph>
        </Card>

        {detail.supporting_evidence && detail.supporting_evidence.length > 0 && (
          <>
            <Divider orientation="left">支持证据</Divider>
            <List
              dataSource={detail.supporting_evidence}
              renderItem={(evidence, index) => (
                <List.Item>
                  <Text>[{index + 1}] {evidence}</Text>
                </List.Item>
              )}
            />
          </>
        )}

        {detail.memories_used && detail.memories_used.length > 0 && (
          <>
            <Divider orientation="left">使用的记忆</Divider>
            <Alert
              message="Agent从记忆库中检索到以下相关经验"
              description="这些记忆来自历史实验的成功/失败经验，帮助Agent做出更准确的推荐"
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <List
              dataSource={detail.memories_used}
              renderItem={(memory, index) => (
                <List.Item>
                  <Card
                    type="inner"
                    size="small"
                    title={
                      <Space>
                        <Text strong>[记忆 {index + 1}] {memory.title}</Text>
                        <Tag
                          color={memory.is_from_success ? 'success' : 'error'}
                          icon={memory.is_from_success ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                        >
                          {memory.is_from_success ? '成功经验' : '失败教训'}
                        </Tag>
                      </Space>
                    }
                    style={{ width: '100%' }}
                  >
                    <Paragraph>
                      <Text type="secondary">描述：</Text>
                      {memory.description}
                    </Paragraph>
                    <Paragraph style={{ marginBottom: 0 }}>
                      <Text type="secondary">内容：</Text>
                      <div style={{ marginTop: 8, whiteSpace: 'pre-wrap', background: '#f5f5f5', padding: '8px', borderRadius: '4px' }}>
                        {memory.content}
                      </div>
                    </Paragraph>
                  </Card>
                </List.Item>
              )}
            />
          </>
        )}

        <Divider orientation="left">生成轨迹</Divider>
        <Card type="inner">
          <List
            dataSource={detail.trajectory.steps.filter(
              (step) => step.action !== 'unknown' && step.reasoning && step.reasoning.trim() !== ''
            )}
            renderItem={(step, index) => (
              <List.Item>
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Text strong>步骤 {index + 1}: {step.action}</Text>
                  <Paragraph style={{ marginLeft: 16, marginBottom: 0 }}>
                    {step.reasoning}
                  </Paragraph>
                  {step.tool && (
                    <Tag color="purple">工具: {step.tool}</Tag>
                  )}
                  {step.num_memories !== null && step.num_memories !== undefined && (
                    <Tag color="cyan">检索到记忆数: {step.num_memories}</Tag>
                  )}
                </Space>
              </List.Item>
            )}
          />
        </Card>

        {detail.experiment_result && (
          <>
            <Divider orientation="left">实验结果</Divider>
            <Alert
              message={
                detail.experiment_result.is_liquid_formed
                  ? '液体形成成功'
                  : '液体形成失败'
              }
              type={detail.experiment_result.is_liquid_formed ? 'success' : 'error'}
              icon={
                detail.experiment_result.is_liquid_formed ? (
                  <CheckCircleOutlined />
                ) : (
                  <CloseCircleOutlined />
                )
              }
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Descriptions bordered column={2}>
              {detail.experiment_result.solubility !== undefined && detail.experiment_result.solubility !== null && (
                <Descriptions.Item label="溶解度" span={2}>
                  <Text strong style={{ fontSize: '16px' }}>
                    {detail.experiment_result.solubility}{' '}
                    {detail.experiment_result.solubility_unit}
                  </Text>
                </Descriptions.Item>
              )}
              {detail.experiment_result.experimenter && (
                <Descriptions.Item label="实验人员">
                  {detail.experiment_result.experimenter}
                </Descriptions.Item>
              )}
              {detail.experiment_result.properties &&
                Object.keys(detail.experiment_result.properties).length > 0 && (
                  <Descriptions.Item label="其他性质" span={2}>
                    {Object.entries(detail.experiment_result.properties).map(
                      ([key, value]) => (
                        <Tag key={key}>
                          {key}: {String(value)}
                        </Tag>
                      )
                    )}
                  </Descriptions.Item>
                )}
              {detail.experiment_result.notes && (
                <Descriptions.Item label="备注" span={2}>
                  {detail.experiment_result.notes}
                </Descriptions.Item>
              )}
              <Descriptions.Item label="实验日期" span={2}>
                {dayjs(detail.experiment_result.experiment_date).format(
                  'YYYY-MM-DD HH:mm:ss'
                )}
              </Descriptions.Item>
            </Descriptions>
          </>
        )}
      </Card>
    </div>
  );
}

export default RecommendationDetailPage;
