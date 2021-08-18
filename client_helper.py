import sys
import torch
import bit_helper
import pickle
import requests
import time
import json
import hashlib
import traceback
import gzip
debug = False
google_cloud = True
HOST = "http://mc.vcccz.com:15000"
if google_cloud:
    HOST = "http://cf.vcccz.com"
if debug:
    HOST = "http://127.0.0.1:5000"

def pack_item(item):
    return {
        "shape": list(item.shape),
        "bits": bit_helper.packbits(item).tolist()
    }

def unpack_item(item):
    return bit_helper.unpackbits(torch.tensor(item["bits"], dtype=torch.int8), item["shape"])

def pack_batch(batch):
    data = {
        "done": pack_item(torch.tensor(batch["done"], dtype=torch.int8)),
        "episode_return": batch["episode_return"].tolist(),
        "target": batch["target"].tolist(),
        "obs_x_batch": pack_item(torch.tensor(batch["obs_x_batch"], dtype=torch.int8)),
        "obs_z": pack_item(torch.tensor(batch["obs_z"], dtype=torch.int8)),
        "obs_type": batch["obs_type"].tolist()
    }
    return data


def unpack_batch(data):
    batch = {
        "done": torch.tensor(unpack_item(data["done"]), dtype=torch.bool),
        "episode_return": torch.tensor(data["episode_return"], dtype=torch.float32),
        "target": torch.tensor(data["target"], dtype=torch.float32),
        "obs_x_batch": unpack_item(data["obs_x_batch"]),
        "obs_z": unpack_item(data["obs_z"]),
        "obs_type": torch.tensor(data["obs_type"], dtype=torch.int8)
    }
    return batch

data_total = 0
start_time = time.time()

def handle_batch(position, batch, model_version, program_version):
    try:
        data = pickle.dumps({"position" : position,  "batch": pack_batch(batch), "model_version": model_version, "program_version": program_version})
        data = gzip.compress(data)
        rep = requests.post(HOST + "/upload_batch", data, headers={'Content-Type': 'application/octet-stream', 'Content-Encoding': 'gzip','Accept-encoding': 'gzip' })
        ret = rep.json()
        if "server_speed" in ret:
            print("上传成功，服务器当前速度: %.1f fps" % ret["server_speed"])
        if "model_version" in ret:
            return ret["model_version"], ret["model_url"]
    except:
        print("Batch 传送失败")
        return model_version, ""

def handle_batches(batches, model_version, program_version):
    data = []

    for batch in batches:
        data.append({
            "position": batch["position"],
            "batch": pack_batch(batch["batch"]),
        })
    info = {
        "batches": data,
        "model_version": model_version,
        "program_version": program_version
    }
    # print(batches)
    data = pickle.dumps(info)
    data = gzip.compress(data)
    tryCount = 2
    rep = None
    print("准备发送Batch")
    try:
        try:
            rep = requests.post(HOST + "/upload_batch", data, headers={'Content-Type': 'application/octet-stream', 'Content-Encoding': 'gzip','Accept-encoding': 'gzip'}, timeout=60)
        except TimeoutError:
            rep = None
            print("传输超时")
        while (rep is None or rep.status_code != 200) and tryCount > 0:
            tryCount -= 1
            print("传输失败，重试中")
            try:
                rep = requests.post(HOST + "/upload_batch", data, headers={'Content-Type': 'application/octet-stream', 'Content-Encoding': 'gzip','Accept-encoding': 'gzip'}, timeout=60)
            except TimeoutError:
                rep = None
                print("传输超时")
        if rep is not None and rep.status_code == 200:
            try:
                ret = rep.json()
                if "info" in ret:
                    print("传输错误: ", ret["info"])
                print(ret)
                if "server_speed" in ret:
                    print("上传成功，服务器当前速度: %.1f fps" % ret["server_speed"])
                if "model_info" in ret:
                    return ret["model_info"]["version"], ret["model_info"]["urls"]
                else:
                    return -1, ""
            except json.JSONDecodeError:
                print("Json Decode Error")
    except Exception as e:
        print("Batch传送失败:", repr(e))

    return model_version, ""

def get_model_info():
    try:
        rep = requests.get(HOST + "/model_info")
        info = rep.json()
        return info
    except:
        print("获取模型版本失败！")
        return None

def download_obj(url):
    req = requests.get(url)
    return req.content

def download_pkl(url):
    try:
        return pickle.loads(download_obj(url))
    except:
        return None
