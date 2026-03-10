#!/bin/bash

# HTTP 服务测试脚本

echo "================================"
echo "视频分析 MCP 服务测试"
echo "================================"
echo ""

# 测试健康检查端点
echo "1. 测试健康检查端点..."
echo "   GET http://localhost:8000/health"
echo ""
curl -s http://localhost:8000/health | python -m json.tool
echo ""
echo ""

# 测试 MCP 端点（无认证）
echo "2. 测试 MCP 端点（无认证，应该失败）..."
echo "   POST http://localhost:8000/mcp"
echo ""
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"test"}' | python -m json.tool
echo ""
echo ""

# 测试 MCP 端点（带认证）
echo "3. 测试 MCP 端点（带认证，应该成功）..."
echo "   POST http://localhost:8000/mcp"
echo "   Authorization: Bearer test-key"
echo ""
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-key" \
  -d '{"jsonrpc":"2.0","id":1,"method":"test"}' | python -m json.tool
echo ""
echo ""

echo "================================"
echo "测试完成"
echo "================================"
