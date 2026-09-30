def test_department_skill_and_employee_crud_and_filters(client):
    d=client.post("/api/departments",json={"name":"Operations"}); assert d.status_code==201; did=d.json()["id"]
    assert client.get(f"/api/departments/{did}").json()["name"]=="Operations"
    assert client.put(f"/api/departments/{did}",json={"name":"Ops","description":"Updated"}).json()["name"]=="Ops"
    s=client.post("/api/skills",json={"name":"First Aid"}); assert s.status_code==201; sid=s.json()["id"]
    assert client.get(f"/api/skills/{sid}").status_code==200
    assert client.put(f"/api/skills/{sid}",json={"name":"First Aid 2"}).status_code==200
    e=client.post("/api/employees",json={"name":"Ari Chen","email":"ari@example.test","department_id":did}); assert e.status_code==201; eid=e.json()["id"]
    assert client.get(f"/api/employees/{eid}").status_code==200
    assert client.get("/api/employees",params={"department_id":did,"active":True}).json()[0]["id"]==eid
    assert client.put(f"/api/employees/{eid}",json={"name":"Ari C","email":"ari@example.test","department_id":did,"active":False}).status_code==200
    assert client.get("/api/employees",params={"active":True}).json()==[]
    assert client.post(f"/api/employees/{eid}/skills",json={"skill_id":sid}).status_code==201
    assert client.post(f"/api/employees/{eid}/skills",json={"skill_id":sid}).status_code==409
    assert client.delete(f"/api/employees/{eid}/skills/{sid}").status_code==204
    assert client.delete(f"/api/employees/{eid}").status_code==204
    assert client.delete(f"/api/skills/{sid}").status_code==204
    assert client.delete(f"/api/departments/{did}").status_code==204

def test_shift_template_shift_skills_and_filters(client):
    d=client.post("/api/departments",json={"name":"Care"}).json()
    sk=client.post("/api/skills",json={"name":"Nursing"}).json()
    t=client.post("/api/shift-templates",json={"name":"Day","start_time":"08:00","end_time":"16:00"}); assert t.status_code==201
    sh=client.post("/api/shifts",json={"date":"2026-10-01","department_id":d["id"],"template_id":t.json()["id"],"required_staff":2}); assert sh.status_code==201; sid=sh.json()["id"]
    assert client.get(f"/api/shifts/{sid}").status_code==200
    assert client.get("/api/shifts",params={"date":"2026-10-01","department_id":d["id"]}).json()[0]["id"]==sid
    assert client.put(f"/api/shifts/{sid}",json={"date":"2026-10-02","department_id":d["id"],"template_id":t.json()["id"],"required_staff":1}).status_code==200
    assert client.post(f"/api/shifts/{sid}/skills",json={"skill_id":sk["id"]}).status_code==201
    assert client.post(f"/api/shifts/{sid}/skills",json={"skill_id":sk["id"]}).status_code==409
    assert client.delete(f"/api/shifts/{sid}/skills/{sk['id']}").status_code==204
    assert client.delete(f"/api/shifts/{sid}").status_code==204
    assert client.delete(f"/api/shift-templates/{t.json()['id']}").status_code==204

def test_availability_leave_preference_and_projects(client):
    emp=client.post("/api/employees",json={"name":"Sam","email":"sam@example.test"}).json(); eid=emp["id"]
    av=client.post("/api/availability",json={"employee_id":eid,"date":"2026-10-01","available":True}); assert av.status_code==201; aid=av.json()["id"]
    assert client.get("/api/availability",params={"employee_id":eid,"date":"2026-10-01"}).json()[0]["id"]==aid
    assert client.put(f"/api/availability/{aid}",json={"employee_id":eid,"date":"2026-10-01","available":False}).status_code==200
    assert client.delete(f"/api/availability/{aid}").status_code==204
    lv=client.post("/api/leave",json={"employee_id":eid,"start_date":"2026-10-02","end_date":"2026-10-03"}); assert lv.status_code==201; lid=lv.json()["id"]
    assert client.get("/api/leave",params={"employee_id":eid}).json()[0]["id"]==lid
    assert client.put(f"/api/leave/{lid}",json={"employee_id":eid,"start_date":"2026-10-02","end_date":"2026-10-04","status":"approved"}).status_code==200
    assert client.delete(f"/api/leave/{lid}").status_code==204
    pref=client.post("/api/preferences",json={"employee_id":eid,"key":"weekend","value":"avoid"}); assert pref.status_code==201; pid=pref.json()["id"]; assert pref.json()["weight"]==1.0
    assert client.put(f"/api/preferences/{pid}",json={"employee_id":eid,"key":"weekend","value":"prefer"}).status_code==200
    assert client.delete(f"/api/preferences/{pid}").status_code==204
    project=client.post("/api/projects",json={"name":"Launch","status":"active"}); assert project.status_code==201; pr=project.json(); assert client.get(f"/api/projects/{pr['id']}").status_code==200
    skill=client.post("/api/skills",json={"name":"Setup"}).json()
    req=client.post(f"/api/projects/{pr['id']}/requirements",json={"skill_id":skill["id"],"role":"technician","quantity":2}); assert req.status_code==201
    assert client.post(f"/api/projects/{pr['id']}/requirements",json={"skill_id":skill['id'],"role":"technician","quantity":2}).status_code==409
    assert client.delete(f"/api/projects/{pr['id']}/requirements/{req.json()['id']}").status_code==204
    assert client.put(f"/api/projects/{pr['id']}",json={"name":"Launch 2","status":"complete"}).status_code==200
    assert client.get("/api/projects",params={"status":"complete"}).json()[0]["id"]==pr["id"]

def test_schedule_assignments_conflicts_explanations(client):
    employee=client.post("/api/employees",json={"name":"Lee","email":"lee@example.test"}).json()
    shift=client.post("/api/shifts",json={"date":"2026-10-01","required_staff":1}).json()
    schedule=client.post("/api/schedules",json={"name":"October","start_date":"2026-10-01","end_date":"2026-10-31"}); assert schedule.status_code==201; sid=schedule.json()["id"]
    assert client.get(f"/api/schedules/{sid}").status_code==200
    assignment=client.post(f"/api/schedules/{sid}/assignments",json={"employee_id":employee["id"],"shift_id":shift["id"]}); assert assignment.status_code==201; aid=assignment.json()["id"]
    assert client.get(f"/api/schedules/{sid}/assignments").json()[0]["id"]==aid
    assert client.get(f"/api/schedules/{sid}/conflicts").json()==[]
    assert client.get(f"/api/schedules/{sid}/explanations").json()==[]
    assert client.delete(f"/api/schedules/{sid}/assignments/{aid}").status_code==204
    assert client.delete(f"/api/schedules/{sid}").status_code==204

def test_missing_resources_and_reference_validation(client):
    assert client.get("/api/departments/404").status_code==404
    assert client.put("/api/departments/404",json={"name":"Missing"}).status_code==404
    assert client.delete("/api/departments/404").status_code==404
    assert client.post("/api/employees",json={"name":"No Dept","email":"bad@example.test","department_id":9876}).status_code==404
    assert client.get("/api/schedules/404/conflicts").status_code==404
