# 验证CSS和JS文件的语法

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "验证文件语法" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 验证CSS文件
Write-Host "1. 验证CSS文件..." -ForegroundColor Yellow
$cssFile = "data_fusion_teaching.css"
$cssContent = Get-Content $cssFile -Raw

# 检查大括号匹配
$openBraces = ([regex]::Matches($cssContent, '\{')).Count
$closeBraces = ([regex]::Matches($cssContent, '\}')).Count

if ($openBraces -eq $closeBraces) {
    Write-Host "   ✓ CSS大括号匹配: $openBraces 个" -ForegroundColor Green
} else {
    Write-Host "   ✗ CSS大括号不匹配: $openBraces 开, $closeBraces 闭" -ForegroundColor Red
}

# 检查注释
if ($cssContent -match '/\s+\*' -and $cssContent -notmatch '/\*') {
    Write-Host "   ✗ CSS注释格式错误" -ForegroundColor Red
} else {
    Write-Host "   ✓ CSS注释格式正确" -ForegroundColor Green
}

Write-Host ""

# 验证JS文件
Write-Host "2. 验证JS文件..." -ForegroundColor Yellow
$jsFile = "data_fusion_teaching.js"

try {
    $result = node -c $jsFile 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   ✓ JS语法正确" -ForegroundColor Green
    } else {
        Write-Host "   ✗ JS语法错误:" -ForegroundColor Red
        Write-Host "   $result" -ForegroundColor Red
    }
} catch {
    Write-Host "   ✗ 无法验证JS文件 (需要安装Node.js)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "验证完成" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
