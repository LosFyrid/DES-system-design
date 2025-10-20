import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Form,
  Input,
  InputNumber,
  Button,
  Card,
  Space,
  Typography,
  Radio,
  Alert,
  Spin,
  message,
  Divider,
  Progress,
  Result,
} from 'antd';
import {
  ArrowLeftOutlined,
  SendOutlined,
  LoadingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined
} from '@ant-design/icons';
import { feedbackService, recommendationService } from '../services';
import type {
  ExperimentResultRequest,
  RecommendationDetail,
  FeedbackStatusData
} from '../types';

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

function FeedbackPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [detail, setDetail] = useState<RecommendationDetail | null>(null);
  const [isLiquidFormed, setIsLiquidFormed] = useState<boolean>(true);

  // Processing status
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStatus, setProcessingStatus] = useState<FeedbackStatusData | null>(null);

  useEffect(() => {
    if (!id) return;

    const fetchDetail = async () => {
      setLoading(true);
      try {
        const response = await recommendationService.getRecommendationDetail(id);
        setDetail(response.data);

        // If already has experiment result, pre-fill the form
        if (response.data.experiment_result) {
          const expResult = response.data.experiment_result;
          form.setFieldsValue({
            is_liquid_formed: expResult.is_liquid_formed,
            solubility: expResult.solubility,
            solubility_unit: expResult.solubility_unit || 'g/L',
            notes: expResult.notes || '',
            // Convert properties object to text format
            properties_text: expResult.properties
              ? Object.entries(expResult.properties)
                  .map(([key, value]) => `${key}=${value}`)
                  .join('\n')
              : '',
          });
          setIsLiquidFormed(expResult.is_liquid_formed);
          message.info('已加载当前反馈数据，您可以修改后重新提交');
        }
      } catch (error) {
        console.error('Failed to fetch recommendation detail:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchDetail();
  }, [id, form]);

  const handleSubmit = async (values: ExperimentResultRequest) => {
    if (!id) return;

    setSubmitting(true);
    try {
      // Submit feedback (async)
      const response = await feedbackService.submitFeedback({
        recommendation_id: id,
        experiment_result: values,
      });

      message.success('反馈已提交，正在后台处理...');

      // Switch to processing mode
      setSubmitting(false);
      setIsProcessing(true);
      setProcessingStatus({
        status: 'processing',
        started_at: new Date().toISOString(),
      });

      // Start polling
      try {
        const finalStatus = await feedbackService.pollStatus(
          id,
          (statusResponse) => {
            // Update status during polling
            setProcessingStatus(statusResponse.data);
          },
          2000, // Poll every 2 seconds
          300000 // 5 minute timeout
        );

        // Processing completed
        setProcessingStatus(finalStatus.data);
        message.success({
          content: `反馈处理完成！提取了 ${finalStatus.data.result?.num_memories || 0} 条记忆`,
          duration: 5,
        });

        // Wait a bit then navigate
        setTimeout(() => {
          navigate(`/recommendations/${id}`);
        }, 2000);

      } catch (pollError: any) {
        console.error('Polling error:', pollError);
        message.error(pollError.message || '处理超时或失败');
        setProcessingStatus({
          status: 'failed',
          started_at: processingStatus?.started_at || new Date().toISOString(),
          failed_at: new Date().toISOString(),
          error: pollError.message || '处理失败',
        });
      }

    } catch (error: any) {
      console.error('Failed to submit feedback:', error);
      message.error(error.response?.data?.message || '提交失败');
      setSubmitting(false);
    }
  };

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

  if (detail.status !== 'PENDING' && detail.status !== 'PROCESSING' && detail.status !== 'COMPLETED') {
    return (
      <Alert
        message="无法提交反馈"
        description={`该推荐的状态为 ${detail.status}，只有待实验或已完成状态的推荐才能提交/更新反馈`}
        type="warning"
        showIcon
      />
    );
  }

  // Show processing status
  if (isProcessing && processingStatus) {
    return (
      <div>
        <Space style={{ marginBottom: 16 }}>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(`/recommendations/${id}`)}
            disabled={processingStatus.status === 'processing'}
          >
            返回详情
          </Button>
        </Space>

        <Card>
          {processingStatus.status === 'processing' && (
            <Result
              icon={<LoadingOutlined style={{ fontSize: 48, color: '#1890ff' }} />}
              title="正在处理反馈..."
              subTitle="系统正在提取实验记忆并更新知识库，这可能需要几秒钟"
              extra={
                <div style={{ textAlign: 'center' }}>
                  <Progress percent={100} status="active" showInfo={false} />
                  <Paragraph style={{ marginTop: 16 }}>
                    <Text type="secondary">
                      开始时间: {new Date(processingStatus.started_at).toLocaleString()}
                    </Text>
                  </Paragraph>
                </div>
              }
            />
          )}

          {processingStatus.status === 'completed' && processingStatus.result && (
            <Result
              status="success"
              icon={<CheckCircleOutlined style={{ fontSize: 48, color: '#52c41a' }} />}
              title="反馈处理完成！"
              subTitle={
                <div>
                  <Paragraph>
                    {processingStatus.result.is_liquid_formed
                      ? `溶解度: ${processingStatus.result.solubility} ${processingStatus.result.solubility_unit}`
                      : 'DES液体未成功形成'}
                  </Paragraph>
                  <Paragraph>
                    提取了 <Text strong>{processingStatus.result.num_memories}</Text> 条记忆
                  </Paragraph>
                  {processingStatus.is_update && processingStatus.deleted_memories !== undefined && processingStatus.deleted_memories > 0 && (
                    <Alert
                      type="warning"
                      message="更新操作"
                      description={`已删除 ${processingStatus.deleted_memories} 条旧记忆并更新为新的实验记忆`}
                      showIcon
                      style={{ marginTop: 8 }}
                    />
                  )}
                </div>
              }
              extra={[
                <Button
                  key="detail"
                  type="primary"
                  onClick={() => navigate(`/recommendations/${id}`)}
                >
                  查看详情
                </Button>,
                <Button key="list" onClick={() => navigate('/recommendations')}>
                  返回列表
                </Button>,
              ]}
            />
          )}

          {processingStatus.status === 'failed' && (
            <Result
              status="error"
              icon={<CloseCircleOutlined style={{ fontSize: 48, color: '#ff4d4f' }} />}
              title="处理失败"
              subTitle={processingStatus.error || '反馈处理过程中发生错误'}
              extra={[
                <Button
                  key="retry"
                  type="primary"
                  onClick={() => {
                    setIsProcessing(false);
                    setProcessingStatus(null);
                  }}
                >
                  重新提交
                </Button>,
                <Button key="back" onClick={() => navigate(`/recommendations/${id}`)}>
                  返回详情
                </Button>,
              ]}
            />
          )}
        </Card>
      </div>
    );
  }

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate(`/recommendations/${id}`)}
        >
          返回详情
        </Button>
      </Space>

      <Title level={2}>
        {detail.status === 'COMPLETED' ? '更新实验反馈' : '提交实验反馈'}
      </Title>
      <Paragraph>
        {detail.status === 'COMPLETED' ? (
          <>
            您正在更新已提交的反馈。系统将删除旧记忆并提取新的实验记忆。
            {detail.experiment_result && (
              <Alert
                type="info"
                message="当前反馈数据"
                description={
                  <div>
                    <div>液体形成：{detail.experiment_result.is_liquid_formed ? '是' : '否'}</div>
                    {detail.experiment_result.solubility && (
                      <div>溶解度：{detail.experiment_result.solubility} {detail.experiment_result.solubility_unit}</div>
                    )}
                  </div>
                }
                showIcon
                style={{ marginTop: 8 }}
              />
            )}
          </>
        ) : (
          '请填写您的实验结果，系统将自动学习并优化未来的推荐。'
        )}
      </Paragraph>

      <Card title="推荐配方信息" style={{ marginBottom: 24 }}>
        <Paragraph>
          <Text strong>配方:</Text> {detail.formulation.HBD} : {detail.formulation.HBA} ({detail.formulation.molar_ratio})
        </Paragraph>
        <Paragraph>
          <Text strong>目标材料:</Text> {detail.task.target_material}
        </Paragraph>
        <Paragraph>
          <Text strong>目标温度:</Text> {detail.task.target_temperature}°C
        </Paragraph>
      </Card>

      <Card title="实验结果">
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{
            is_liquid_formed: true,
            solubility_unit: 'g/L',
          }}
        >
          <Form.Item
            label="DES液体是否成功形成？"
            name="is_liquid_formed"
            rules={[{ required: true, message: '请选择液体是否形成' }]}
          >
            <Radio.Group onChange={(e) => setIsLiquidFormed(e.target.value)}>
              <Radio value={true}>是</Radio>
              <Radio value={false}>否</Radio>
            </Radio.Group>
          </Form.Item>

          {!isLiquidFormed && (
            <Alert
              message="液体未形成"
              description="如果DES液体未能成功形成，请在备注中说明原因（如固体未溶解、分层等）"
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}

          {isLiquidFormed && (
            <>
              <Form.Item
                label="溶解度"
                name="solubility"
                rules={[
                  {
                    required: isLiquidFormed,
                    message: '液体形成时必须填写溶解度',
                  },
                  { type: 'number', min: 0, message: '溶解度必须为正数' },
                ]}
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  step={0.1}
                  placeholder="例如: 8.5"
                  addonAfter={
                    <Form.Item name="solubility_unit" noStyle>
                      <Input style={{ width: 80 }} placeholder="g/L" />
                    </Form.Item>
                  }
                />
              </Form.Item>
            </>
          )}

          <Form.Item
            label="实验温度 (°C)"
            name="temperature"
          >
            <InputNumber
              style={{ width: '100%' }}
              min={-80}
              max={150}
              step={0.1}
              placeholder="实际实验温度"
            />
          </Form.Item>

          <Divider orientation="left">其他性质（可选）</Divider>

          <Form.Item
            label="其他观察到的性质"
            name="properties_text"
            help="每行一个属性，格式: 属性名=值"
          >
            <TextArea
              rows={4}
              placeholder="例如:
viscosity=low
color=transparent
stability=good"
              onChange={(e) => {
                const text = e.target.value;
                if (!text) {
                  form.setFieldValue('properties', undefined);
                  return;
                }

                const properties: Record<string, string> = {};
                const lines = text.split('\n');
                for (const line of lines) {
                  const [key, value] = line.split('=').map((s) => s.trim());
                  if (key && value) {
                    properties[key] = value;
                  }
                }
                form.setFieldValue('properties', properties);
              }}
            />
          </Form.Item>

          <Form.Item name="properties" hidden>
            <Input />
          </Form.Item>

          <Form.Item label="备注" name="notes">
            <TextArea
              rows={3}
              placeholder="请记录实验过程中的任何额外观察、问题或建议"
              showCount
              maxLength={500}
            />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button
                type="primary"
                htmlType="submit"
                icon={<SendOutlined />}
                loading={submitting}
                size="large"
              >
                {detail.status === 'COMPLETED' ? '更新反馈' : '提交反馈'}
              </Button>
              <Button
                onClick={() => navigate(`/recommendations/${id}`)}
                size="large"
              >
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}

export default FeedbackPage;
