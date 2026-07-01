WORKFLOW = {
    "order": 6,
    "workflow_type": "image_to_video",
    "label": "图生视频",
    "aliases": ["img2video", "i2v", "图生视频", "图片生成视频"],
    "template_kind": "simple",
    "title": "图生视频工作流",
    "nodes": [
        (
            "image_input",
            "imageGenNode",
            "图片输入",
            "承载上传图片或已生成图片，作为视频生成的源画面。",
            "image",
        ),
        ("video_output", "videoNode", "生成视频", "根据上游图片生成视频片段。", "video"),
    ],
    "edges": [("image_input", "video_output")],
}
