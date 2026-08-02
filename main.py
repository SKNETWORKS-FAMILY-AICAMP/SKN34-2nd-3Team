from huggingface_hub import snapshot_download

# 1. 허깅페이스에서 데이터셋전체 다운로드
snapshot_download(
    repo_id="SKN34/SKN34-2nd-3Team", 
    local_dir="db/data"
) 

