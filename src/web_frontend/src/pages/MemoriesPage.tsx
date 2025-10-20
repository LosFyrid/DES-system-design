import { useState, useEffect, useCallback } from 'react';
import {
  Table,
  Typography,
  Tag,
  Button,
  Space,
  Card,
  message,
  Modal,
  Form,
  Input,
  Switch,
  Select,
  Popconfirm,
  Descriptions,
  Alert,
} from 'antd';
import {
  EyeOutlined,
  EditOutlined,
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { memoryService } from '../services/memoryService';
import type { MemoryItemDetail, MemoryItemCreate, MemoryItemUpdate } from '../types';

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;
const { Search } = Input;

function MemoriesPage() {
  const [loading, setLoading] = useState(false);
  const [memories, setMemories] = useState<MemoryItemDetail[]>([]);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // Filters
  const [isFromSuccessFilter, setIsFromSuccessFilter] = useState<boolean | undefined>(undefined);
  const [sourceTaskIdFilter, setSourceTaskIdFilter] = useState<string | undefined>(undefined);

  // Modals
  const [viewModalVisible, setViewModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [selectedMemory, setSelectedMemory] = useState<MemoryItemDetail | null>(null);

  // Forms
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();

  const fetchMemories = useCallback(async () => {
    setLoading(true);
    try {
      const response = await memoryService.listMemories({
        page: currentPage,
        page_size: pageSize,
        is_from_success: isFromSuccessFilter,
        source_task_id: sourceTaskIdFilter,
      });
      setMemories(response.data.items);
      setTotal(response.data.pagination.total);
    } catch (error) {
      console.error('Failed to fetch memories:', error);
      message.error('获取记忆列表失败');
    } finally {
      setLoading(false);
    }
  }, [currentPage, pageSize, isFromSuccessFilter, sourceTaskIdFilter]);

  useEffect(() => {
    fetchMemories();
  }, [fetchMemories]);

  const handleViewMemory = (memory: MemoryItemDetail) => {
    setSelectedMemory(memory);
    setViewModalVisible(true);
  };

  const handleEditMemory = (memory: MemoryItemDetail) => {
    setSelectedMemory(memory);
    editForm.setFieldsValue({
      description: memory.description,
      content: memory.content,
      is_from_success: memory.is_from_success,
    });
    setEditModalVisible(true);
  };

  const handleDeleteMemory = async (title: string) => {
    try {
      await memoryService.deleteMemory(title);
      message.success('记忆删除成功');
      fetchMemories();
    } catch (error) {
      console.error('Failed to delete memory:', error);
      message.error('删除记忆失败');
    }
  };

  const handleCreateMemory = async (values: MemoryItemCreate) => {
    try {
      await memoryService.createMemory(values);
      message.success('记忆创建成功');
      setCreateModalVisible(false);
      createForm.resetFields();
      fetchMemories();
    } catch (error: any) {
      console.error('Failed to create memory:', error);
      message.error(error.response?.data?.detail || '创建记忆失败');
    }
  };

  const handleUpdateMemory = async (values: MemoryItemUpdate) => {
    if (!selectedMemory) return;

    try {
      await memoryService.updateMemory(selectedMemory.title, values);
      message.success('记忆更新成功');
      setEditModalVisible(false);
      editForm.resetFields();
      setSelectedMemory(null);
      fetchMemories();
    } catch (error: any) {
      console.error('Failed to update memory:', error);
      message.error(error.response?.data?.detail || '更新记忆失败');
    }
  };

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: 200,
      ellipsis: true,
      render: (title: string) => (
        <Typography.Text strong>{title}</Typography.Text>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '来源',
      dataIndex: 'is_from_success',
      key: 'is_from_success',
      width: 100,
      render: (isFromSuccess: boolean) => (
        <Tag
          color={isFromSuccess ? 'success' : 'error'}
          icon={isFromSuccess ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
        >
          {isFromSuccess ? '成功' : '失败'}
        </Tag>
      ),
    },
    {
      title: '关联任务',
      dataIndex: 'source_task_id',
      key: 'source_task_id',
      width: 150,
      ellipsis: true,
      render: (taskId?: string) => (
        taskId ? <Typography.Text code>{taskId}</Typography.Text> : <Text type="secondary">-</Text>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right' as const,
      width: 200,
      render: (_: unknown, record: MemoryItemDetail) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleViewMemory(record)}
          >
            查看
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEditMemory(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确认删除"
            description={`确定要删除记忆 "${record.title}" 吗？此操作不可撤销。`}
            onConfirm={() => handleDeleteMemory(record.title)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Title level={2}>记忆库管理</Title>
      <Paragraph>
        管理Agent的推理记忆。记忆来源于实验反馈的自动提取，也可手动创建和编辑。
      </Paragraph>

      <Alert
        message="关于记忆库"
        description="记忆库存储从成功/失败实验中提取的推理策略。Agent在生成新推荐时会检索相关记忆来指导决策。"
        type="info"
        showIcon
        closable
        style={{ marginBottom: 16 }}
      />

      {/* Filter Card */}
      <Card style={{ marginBottom: 16 }}>
        <Space size="middle" wrap>
          <span>来源筛选:</span>
          <Select
            placeholder="全部"
            allowClear
            style={{ width: 120 }}
            value={isFromSuccessFilter}
            onChange={(value) => {
              setIsFromSuccessFilter(value);
              setCurrentPage(1);
            }}
            options={[
              { label: '全部', value: undefined },
              { label: '成功实验', value: true },
              { label: '失败实验', value: false },
            ]}
          />

          <span>任务ID:</span>
          <Search
            placeholder="输入任务/推荐ID"
            allowClear
            style={{ width: 250 }}
            value={sourceTaskIdFilter}
            onChange={(e) => {
              const value = e.target.value;
              if (!value) {
                setSourceTaskIdFilter(undefined);
                setCurrentPage(1);
              }
            }}
            onSearch={(value) => {
              setSourceTaskIdFilter(value || undefined);
              setCurrentPage(1);
            }}
          />

          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              setIsFromSuccessFilter(undefined);
              setSourceTaskIdFilter(undefined);
              setCurrentPage(1);
              fetchMemories();
            }}
          >
            重置
          </Button>

          <Button
            type="primary"
            icon={<ReloadOutlined />}
            onClick={fetchMemories}
            loading={loading}
          >
            刷新
          </Button>

          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              createForm.resetFields();
              setCreateModalVisible(true);
            }}
          >
            新建记忆
          </Button>
        </Space>
      </Card>

      {/* Table */}
      <Card>
        <Table
          columns={columns}
          dataSource={memories}
          rowKey="title"
          loading={loading}
          scroll={{ x: 1200 }}
          pagination={{
            current: currentPage,
            pageSize: pageSize,
            total: total,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条记忆`,
            onChange: (page, size) => {
              setCurrentPage(page);
              setPageSize(size);
            },
          }}
          locale={{
            emptyText: '暂无记忆数据',
          }}
        />
      </Card>

      {/* View Modal */}
      <Modal
        title="记忆详情"
        open={viewModalVisible}
        onCancel={() => {
          setViewModalVisible(false);
          setSelectedMemory(null);
        }}
        footer={[
          <Button key="close" onClick={() => setViewModalVisible(false)}>
            关闭
          </Button>,
          <Button
            key="edit"
            type="primary"
            icon={<EditOutlined />}
            onClick={() => {
              setViewModalVisible(false);
              if (selectedMemory) {
                handleEditMemory(selectedMemory);
              }
            }}
          >
            编辑
          </Button>,
        ]}
        width={800}
      >
        {selectedMemory && (
          <Descriptions column={1} bordered>
            <Descriptions.Item label="标题">
              {selectedMemory.title}
            </Descriptions.Item>
            <Descriptions.Item label="描述">
              {selectedMemory.description}
            </Descriptions.Item>
            <Descriptions.Item label="详细内容">
              <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontFamily: 'inherit' }}>
                {selectedMemory.content}
              </pre>
            </Descriptions.Item>
            <Descriptions.Item label="来源">
              <Tag
                color={selectedMemory.is_from_success ? 'success' : 'error'}
                icon={selectedMemory.is_from_success ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
              >
                {selectedMemory.is_from_success ? '成功实验' : '失败实验'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="关联任务">
              {selectedMemory.source_task_id || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">
              {dayjs(selectedMemory.created_at).format('YYYY-MM-DD HH:mm:ss')}
            </Descriptions.Item>
            {Object.keys(selectedMemory.metadata).length > 0 && (
              <Descriptions.Item label="元数据">
                <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontFamily: 'monospace', fontSize: '12px' }}>
                  {JSON.stringify(selectedMemory.metadata, null, 2)}
                </pre>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>

      {/* Create Modal */}
      <Modal
        title="新建记忆"
        open={createModalVisible}
        onCancel={() => {
          setCreateModalVisible(false);
          createForm.resetFields();
        }}
        onOk={() => createForm.submit()}
        okText="创建"
        cancelText="取消"
        width={800}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreateMemory}
        >
          <Form.Item
            name="title"
            label="标题"
            rules={[
              { required: true, message: '请输入标题' },
              { max: 200, message: '标题不能超过200字符' },
            ]}
          >
            <Input placeholder="简短的记忆标题（1-200字符）" />
          </Form.Item>

          <Form.Item
            name="description"
            label="描述"
            rules={[
              { required: true, message: '请输入描述' },
              { max: 500, message: '描述不能超过500字符' },
            ]}
          >
            <Input placeholder="一句话描述记忆内容（1-500字符）" />
          </Form.Item>

          <Form.Item
            name="content"
            label="详细内容"
            rules={[
              { required: true, message: '请输入详细内容' },
              { max: 2000, message: '内容不能超过2000字符' },
            ]}
          >
            <TextArea
              rows={8}
              placeholder="详细的记忆内容和推理策略（1-2000字符）"
            />
          </Form.Item>

          <Form.Item
            name="is_from_success"
            label="来源��型"
            valuePropName="checked"
            initialValue={true}
          >
            <Switch
              checkedChildren="成功实验"
              unCheckedChildren="失败实验"
            />
          </Form.Item>

          <Form.Item
            name="source_task_id"
            label="关联任务ID"
          >
            <Input placeholder="（可选）关联的任务或推荐ID" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit Modal */}
      <Modal
        title={`编辑记忆: ${selectedMemory?.title}`}
        open={editModalVisible}
        onCancel={() => {
          setEditModalVisible(false);
          editForm.resetFields();
          setSelectedMemory(null);
        }}
        onOk={() => editForm.submit()}
        okText="保存"
        cancelText="取消"
        width={800}
      >
        <Alert
          message="注意"
          description="标题不可修改。如需更改标题，请删除后重新创建。"
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <Form
          form={editForm}
          layout="vertical"
          onFinish={handleUpdateMemory}
        >
          <Form.Item
            name="description"
            label="描述"
            rules={[
              { required: true, message: '请输入描述' },
              { max: 500, message: '描述不能超过500字符' },
            ]}
          >
            <Input placeholder="一句话描述记忆内容（1-500字符）" />
          </Form.Item>

          <Form.Item
            name="content"
            label="详细内容"
            rules={[
              { required: true, message: '请输入详细内容' },
              { max: 2000, message: '内容不能超过2000字符' },
            ]}
          >
            <TextArea
              rows={8}
              placeholder="详细的记忆内容和推理策略（1-2000字符）"
            />
          </Form.Item>

          <Form.Item
            name="is_from_success"
            label="来源类型"
            valuePropName="checked"
          >
            <Switch
              checkedChildren="成功实验"
              unCheckedChildren="失败实验"
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

export default MemoriesPage;
