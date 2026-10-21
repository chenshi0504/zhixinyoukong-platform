/**
 * 多源数据融合 - 图表显示和CSV导出修复
 */

// 正确的图表路径
const CHART_BASE_PATH = '../../../backend/algorithms/多源数据融合/visualization_results/';

/**
 * 生成融合分析图表 - 分开展示
 */
function generateFusionCharts() {
    const visualizationDisplay = document.getElementById('visualizationDisplay');
    
    if (!visualizationDisplay) {
        console.error('找不到可视化显示区域');
        return;
    }
    
    const content = `
        <div class="fusion-charts-container" style="width: 100%;">
            <h4 style="color: #2C5AA0; margin-bottom: 30px; font-size: 20px; text-align: center;">数据融合分析结果</h4>
            
            <!-- 图表展示区 -->
            <div style="display: grid; grid-template-columns: 1fr; gap: 30px;">
                <!-- 图表1 -->
                <div class="chart-item" style="background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <img src="${CHART_BASE_PATH}fusion_overview_analysis.png" alt="融合概览分析" 
                         style="max-width: 100%; height: auto; border-radius: 8px; display: block; margin: 0 auto;"
                         onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                    <div style="display: none; padding: 40px; background: #f8f9fa; border-radius: 8px; text-align: center; color: #999;">
                        <div style="font-size: 48px; margin-bottom: 10px;">📊</div>
                        <p style="font-size: 14px;">图表未找到，请运行后端算法生成</p>
                    </div>
                </div>
                
                <!-- 图表2 -->
                <div class="chart-item" style="background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <img src="${CHART_BASE_PATH}detailed_performance_analysis.png" alt="详细性能分析" 
                         style="max-width: 100%; height: auto; border-radius: 8px; display: block; margin: 0 auto;"
                         onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                    <div style="display: none; padding: 40px; background: #f8f9fa; border-radius: 8px; text-align: center; color: #999;">
                        <div style="font-size: 48px; margin-bottom: 10px;">📈</div>
                        <p style="font-size: 14px;">图表未找到，请运行后端算法生成</p>
                    </div>
                </div>
                
                <!-- 图表3 -->
                <div class="chart-item" style="background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <img src="${CHART_BASE_PATH}fusion_algorithm_demo.png" alt="融合算法演示" 
                         style="max-width: 100%; height: auto; border-radius: 8px; display: block; margin: 0 auto;"
                         onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                    <div style="display: none; padding: 40px; background: #f8f9fa; border-radius: 8px; text-align: center; color: #999;">
                        <div style="font-size: 48px; margin-bottom: 10px;">🔬</div>
                        <p style="font-size: 14px;">图表未找到，请运行后端算法生成</p>
                    </div>
                </div>
            </div>
            
            <!-- CSV导出 -->
            <div style="margin-top: 30px; background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center;">
                <button onclick="exportFusionData()" style="padding: 12px 32px; background: #28a745; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 15px; font-weight: 500; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    📥 导出融合数据 (CSV)
                </button>
            </div>
        </div>
    `;
    
    visualizationDisplay.innerHTML = content;
    alert('融合分析图表生成成功！');
}

/**
 * 导出融合数据CSV
 */
function exportFusionData() {
    const csvPath = CHART_BASE_PATH + 'fusion_data.csv';
    
    // 尝试读取CSV文件
    fetch(csvPath)
        .then(response => {
            if (!response.ok) {
                throw new Error('CSV文件未找到');
            }
            return response.blob();
        })
        .then(blob => {
            // 创建下载链接
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `多源数据融合结果_${new Date().toISOString().slice(0,10)}.csv`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
            
            alert('融合数据导出成功！\n文件包含YOLO检测、LiDAR点云和融合结果等信息');
        })
        .catch(error => {
            console.error('导出失败:', error);
            alert('导出失败：CSV文件未找到\n请先运行后端算法生成融合数据\n路径：' + csvPath);
        });
}

// 页面加载时绑定事件
document.addEventListener('DOMContentLoaded', function() {
    // 查找生成图表按钮并绑定事件
    const generateBtn = document.getElementById('generateVisualizationBtn') || 
                        document.getElementById('generateFusionChartsBtn');
    if (generateBtn) {
        generateBtn.addEventListener('click', generateFusionCharts);
    }
    
    console.log('融合图表修复脚本已加载');
});
