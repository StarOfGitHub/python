from r3sourcer.apps.company_settings import permissions


class TestBaseEndpointPermission:
    permission = permissions.BaseEndpointPermission()
    permission.permission_name = 'permission'
    url = '/dummy/url'

    def test_get_request(self, rf, user, permission_get):
        user.user_permissions.add(permission_get)
        request = rf.get(self.url)
        request.user = user

        assert self.permission.has_permission(request, None)

    def test_post_request(self, rf, user, permission_post):
        user.user_permissions.add(permission_post)
        request = rf.post(self.url)
        request.user = user

        assert self.permission.has_permission(request, None)

    def test_patch_request(self, rf, user, permission_patch):
        user.user_permissions.add(permission_patch)
        request = rf.patch(self.url)
        request.user = user

        assert self.permission.has_permission(request, None)

    def test_delete_request(self, rf, user, permission_delete):
        user.user_permissions.add(permission_delete)
        request = rf.delete(self.url)
        request.user = user

        assert self.permission.has_permission(request, None)

    def test_request_without_permission(self, rf, user):
        request = rf.get(self.url)
        request.user = user

        assert not self.permission.has_permission(request, None)
